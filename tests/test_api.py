"""Exercise the MiniJ client against real local HTTP responses."""

import importlib.util
from pathlib import Path

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web

# Load the transport alone, without executing the Home Assistant component.
spec = importlib.util.spec_from_file_location(
    "minij_api", Path(__file__).parents[1] / "custom_components/minij/api.py"
)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


@pytest_asyncio.fixture
async def service(unused_tcp_port, monkeypatch):
    routes = web.RouteTableDef()
    state = {"status": 200, "body": {"success": True, "data": []}, "requests": []}

    @routes.route("*", "/api/{route:.*}")
    async def handle(request):
        state["requests"].append(request)
        if request.method == "POST":
            state["request_body"] = await request.json()
        if "raw_body" in state:
            return web.Response(text=state["raw_body"], content_type="application/json")
        return web.json_response(
            state["body"], status=state["status"], headers=state.get("headers")
        )

    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
    monkeypatch.setattr(api, "API_BASE", f"http://127.0.0.1:{unused_tcp_port}/api/")
    async with aiohttp.ClientSession() as session:
        yield api.MinijClient(session, "test-token"), state
    await runner.cleanup()


async def test_real_request_headers_and_opaque_device_id(service):
    client, state = service
    devices = [
        {
            "deviceId": "washer-001",
            "deviceCharacterMap": {"current_status_alias": "resting"},
        }
    ]
    state["body"]["data"] = devices
    assert await client.async_get_devices() == devices
    request = state["requests"][0]
    assert request.method == "GET"
    assert request.path == "/api/device/getUserBindDeviceList"
    assert request.headers["token"] == "test-token"
    assert request.headers["platform"] == "WEBSITE"
    assert request.headers["version"] == "1.3.0"


@pytest.mark.parametrize("status", [401, 403])
async def test_rejected_sessions_are_auth_failures(service, status):
    client, state = service
    state["status"] = status
    state["body"] = {"success": False, "errorMessage": "private-server-message"}
    with pytest.raises(api.MinijAuthError) as error:
        await client.async_get_devices()
    assert "test-token" not in str(error.value)
    assert "private-server-message" not in str(error.value)


@pytest.mark.parametrize(
    "body",
    [
        {"success": False, "data": []},
        {"success": True, "data": {}},
        {"success": True, "data": [None]},
        {"success": True, "data": [{"deviceId": ""}]},
        {"success": True, "data": [{"deviceId": "same"}, {"deviceId": "same"}]},
        {"success": True, "data": [{"deviceId": "one", "deviceCharacterMap": []}]},
    ],
)
async def test_malformed_status_is_not_accepted_as_empty_success(service, body):
    client, state = service
    state["body"] = body
    with pytest.raises(api.MinijError):
        await client.async_get_devices()


async def test_profile_excludes_private_data(service):
    client, state = service
    state["body"]["data"] = {
        "userId": "account-001",
        "token": "private",
        "phone": "private",
    }
    assert await client.async_get_profile() == {"userId": "account-001"}


async def test_cloud_outage_is_not_an_auth_failure(service):
    client, state = service
    state["status"] = 503
    with pytest.raises(api.MinijError) as error:
        await client.async_get_devices()
    assert not isinstance(error.value, api.MinijAuthError)


async def test_redirect_is_not_followed_with_session_credentials(service):
    client, state = service
    state["status"] = 302
    with pytest.raises(api.MinijError, match="HTTP 302"):
        await client.async_get_devices()
    assert len(state["requests"]) == 1


async def test_sms_request_uses_login_type_without_existing_token(service):
    client, state = service
    state["body"]["data"] = None
    assert await client.async_request_sms(" 13800000000 ") is None
    request = state["requests"][0]
    assert request.method == "POST"
    assert request.path == "/api/captcha/sendSmsCaptcha"
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["platform"] == "WEBSITE"
    assert request.headers["version"] == "1.3.0"
    assert "token" not in request.headers
    assert state["request_body"] == {"phone": "13800000000", "type": "login"}
    assert len(state["requests"]) == 1


async def test_sms_login_returns_only_token_and_does_not_mutate_client(service):
    client, state = service
    state["body"]["data"] = {
        "token": " new-session ",
        "phone": "13800000000",
        "userId": "account-001",
    }
    assert await client.async_login("13800000000", " 012345 ") == "new-session"
    request = state["requests"][0]
    assert request.path == "/api/login/loginByPhone"
    assert request.method == "POST"
    assert "token" not in request.headers
    assert state["request_body"] == {"phone": "13800000000", "captcha": "012345"}
    state["body"]["data"] = []
    await client.async_get_devices()
    assert state["requests"][-1].headers["token"] == "test-token"


@pytest.mark.parametrize("data", [None, [], {}, {"token": 1}, {"token": " "}])
async def test_login_requires_a_nonempty_string_token(service, data):
    client, state = service
    state["body"]["data"] = data
    with pytest.raises(api.MinijLoginError):
        await client.async_login("13800000000", "012345")


@pytest.mark.parametrize("data", [{"challenge": "private-challenge"}, [], "private", 1])
async def test_unexpected_sms_payload_is_not_treated_as_delivery(service, data):
    client, state = service
    state["body"]["data"] = data
    with pytest.raises(api.MinijLoginError):
        await client.async_request_sms("13800000000")


@pytest.mark.parametrize("operation", ["sms", "login"])
@pytest.mark.parametrize("status", [200, 401, 403, 429, 503, 302])
async def test_login_errors_are_typed_private_and_never_retried(
    service, operation, status, caplog
):
    client, state = service
    state["status"] = status
    state["body"] = {
        "success": False,
        "errorCode": "unknown-private-code",
        "errorMessage": "private-phone-13800000000-code-012345",
        "data": {"token": "private-response-token"},
    }
    expected = (
        api.MinijRateLimitError
        if status == 429
        else api.MinijLoginError
        if status in (200, 401, 403)
        else api.MinijError
    )
    with pytest.raises(expected) as error:
        if operation == "sms":
            await client.async_request_sms("13800000000")
        else:
            await client.async_login("13800000000", "012345")
    assert len(state["requests"]) == 1
    for secret in ("13800000000", "012345", "private", "test-token"):
        assert secret not in str(error.value)
        assert secret not in caplog.text
    assert not isinstance(error.value, api.MinijAuthError)


async def test_malformed_login_json_is_a_connection_response_failure(service):
    client, state = service
    state["raw_body"] = "{private broken response"
    with pytest.raises(api.MinijError) as error:
        await client.async_login("13800000000", "012345")
    assert not isinstance(error.value, api.MinijLoginError)
    assert "private" not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.parametrize("phone,code", [("", "012345"), ("13800000000", " ")])
async def test_missing_login_input_never_sends_a_request(service, phone, code):
    client, state = service
    with pytest.raises(api.MinijLoginError):
        await client.async_login(phone, code)
    assert state["requests"] == []


async def test_sms_boolean_acknowledgement_is_accepted(service):
    client, state = service
    state["body"]["data"] = True
    await client.async_request_sms("13800000000")
    assert len(state["requests"]) == 1


async def test_missing_sms_phone_never_sends_a_request(service):
    client, state = service
    with pytest.raises(api.MinijLoginError):
        await client.async_request_sms(" ")
    assert state["requests"] == []


@pytest.mark.parametrize(
    ("header", "expected"),
    [("1800", 1800), ("0", 0), ("-10", None), ("nonsense", None), ("", None)],
)
async def test_rate_limit_retry_after_without_retrying(service, header, expected):
    client, state = service
    state["status"] = 429
    state["headers"] = {"Retry-After": header}
    with pytest.raises(api.MinijRateLimitError) as error:
        await client.async_get_devices()
    assert error.value.retry_after == expected
    assert len(state["requests"]) == 1


async def test_rate_limit_http_date(service):
    from datetime import UTC, datetime, timedelta
    from email.utils import format_datetime

    client, state = service
    state["status"] = 429
    state["headers"] = {
        "Retry-After": format_datetime(
            datetime.now(UTC) + timedelta(hours=1), usegmt=True
        )
    }
    with pytest.raises(api.MinijRateLimitError) as error:
        await client.async_get_devices()
    assert 3590 < error.value.retry_after <= 3600


def notification_record(identifier="message-test", **overrides):
    return {
        "id": identifier,
        "deviceId": "washer-test",
        "type": "DEVICE_NOTIFICATION",
        "title": "洗衣完成",
        "pushTime": "2026-01-01 12:00:00",
        "content": "private-device-name-and-program",
        **overrides,
    }


async def test_notification_post_is_authenticated_read_without_side_effects(service):
    client, state = service
    state["body"]["data"] = {
        "content": [
            notification_record(),
            notification_record("clean", title="清洁完成"),
            notification_record("fault", title="故障提醒"),
            notification_record(
                "reminder", title="清洁提醒", content="已经完成118次任务"
            ),
            notification_record("future", title="Future notification"),
        ]
    }
    records = await client.async_get_notifications("washer-test")
    assert [record.event_type for record in records] == [
        "wash_completed",
        "cleaning_completed",
        "fault_reported",
        None,
        None,
    ]
    assert "private-device-name" not in repr(records)
    assert state["request_body"] == {
        "type": "DEVICE_NOTIFICATION",
        "deviceId": "washer-test",
    }
    assert len(state["requests"]) == 1
    request = state["requests"][0]
    assert request.method == "POST"
    assert request.path == "/api/notificationCenter/findByPage"
    assert request.headers["token"] == "test-token"


@pytest.mark.parametrize("status", [401, 403])
async def test_notification_auth_rejection_is_not_sms_login_failure(service, status):
    client, state = service
    state["status"] = status
    with pytest.raises(api.MinijAuthError):
        await client.async_get_notifications("washer-test")
    assert len(state["requests"]) == 1


@pytest.mark.parametrize(
    "data",
    [
        [],
        {},
        {"content": None},
        {"content": [None]},
        {"content": [notification_record(id="")]},
        {"content": [notification_record(deviceId="other-device")]},
        {"content": [notification_record(type="SYSTEM")]},
        {"content": [notification_record(pushTime="bad-date")]},
        {"content": [notification_record(pushTime=None)]},
        {"content": [notification_record(), notification_record()]},
    ],
)
async def test_invalid_notification_page_cannot_advance_cursor(service, data):
    client, state = service
    state["body"]["data"] = data
    with pytest.raises(api.MinijError):
        await client.async_get_notifications("washer-test")


@pytest.mark.parametrize("enabled", [True, False])
async def test_child_lock_exact_authenticated_payload_and_single_request(
    service, enabled
):
    client, state = service
    state["body"]["data"] = None
    await client.async_set_child_lock("washer-test", enabled)
    assert len(state["requests"]) == 1
    request = state["requests"][0]
    assert request.path == "/api/device/switchBasicFunction"
    assert request.method == "POST"
    assert request.headers["token"] == "test-token"
    assert state["request_body"] == {
        "deviceId": "washer-test",
        "basicFunction": "childLock",
        "onOff": enabled,
        "bucketCode": "",
    }
    assert type(state["request_body"]["onOff"]) is bool


@pytest.mark.parametrize("enabled", [1, 0, "open", "close", None])
async def test_child_lock_rejects_non_boolean_before_request(service, enabled):
    client, state = service
    with pytest.raises(api.MinijError):
        await client.async_set_child_lock("washer-test", enabled)
    assert not state["requests"]


@pytest.mark.parametrize("status", [401, 403, 429, 500, 302])
async def test_child_lock_failures_are_not_retried(service, status):
    client, state = service
    state["status"] = status
    with pytest.raises(api.MinijError):
        await client.async_set_child_lock("washer-test", True)
    assert len(state["requests"]) == 1


async def test_prompt_tone_settings_uses_escaped_device_query_and_only_exact_code(
    service,
):
    client, state = service
    state["body"]["data"] = {
        "fucntionSettingItemList": [
            {"code": "intelligentBucketClean", "switchStatus": False},
            {"code": "promptTone", "switchStatus": True, "private": "canary"},
        ]
    }
    assert await client.async_get_prompt_tone("washer&other=private") is True
    request = state["requests"][0]
    assert request.method == "GET"
    assert request.path == "/api/device/v3/getDeviceMoreSetting"
    assert dict(request.query) == {"deviceId": "washer&other=private"}
    assert request.headers["token"] == "test-token"


@pytest.mark.parametrize(
    "items,expected",
    [([], None), ([{"code": "promptTone", "switchStatus": False}], False)],
)
async def test_prompt_tone_absence_is_unknown_and_false_is_valid(
    service, items, expected
):
    client, state = service
    state["body"]["data"] = {"fucntionSettingItemList": items}
    assert await client.async_get_prompt_tone("washer-test") is expected


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {},
        {"fucntionSettingItemList": None},
        {"fucntionSettingItemList": [None]},
        *[
            {"fucntionSettingItemList": [{"code": "promptTone", "switchStatus": value}]}
            for value in [None, 0, 1, "open", "true"]
        ],
        {"fucntionSettingItemList": [{"code": "promptTone", "switchStatus": True}] * 2},
    ],
)
async def test_prompt_tone_malformed_setting_never_becomes_false(service, data):
    client, state = service
    state["body"]["data"] = data
    with pytest.raises(api.MinijError):
        await client.async_get_prompt_tone("washer-test")


@pytest.mark.parametrize("enabled", [True, False])
async def test_prompt_tone_exact_web_payload_no_bucket_or_value(service, enabled):
    client, state = service
    await client.async_set_prompt_tone("washer-test", enabled)
    assert state["request_body"] == {
        "deviceId": "washer-test",
        "basicFunction": "promptTone",
        "onOff": enabled,
    }
    assert len(state["requests"]) == 1
    request = state["requests"][0]
    assert request.method == "POST"
    assert request.path == "/api/device/switchBasicFunction"
    assert request.headers["token"] == "test-token"


@pytest.mark.parametrize("status", [401, 403, 429, 500, 302])
async def test_prompt_tone_failure_is_one_request(service, status):
    client, state = service
    state["status"] = status
    with pytest.raises(api.MinijError):
        await client.async_set_prompt_tone("washer-test", True)
    assert len(state["requests"]) == 1


@pytest.mark.parametrize("value", [0, 1, None, "true"])
async def test_prompt_tone_rejects_invalid_action_before_request(service, value):
    client, state = service
    with pytest.raises(api.MinijError):
        await client.async_set_prompt_tone("washer-test", value)
    assert not state["requests"]
