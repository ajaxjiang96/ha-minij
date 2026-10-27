"""Observed cycle-control transport using only a synthetic local HTTP service."""

import json
from unittest.mock import patch

import pytest
from test_api import (
    api,
    service,  # noqa: F401
)


async def test_running_program_escapes_query_and_returns_only_identity(service):  # noqa: F811
    client, state = service
    state["body"]["data"] = {
        "id": "private-running-program",
        "private": "private-response-canary",
    }
    assert (
        await client.async_get_running_program("device&other=1+?#/筒")
        == "private-running-program"
    )
    assert len(state["requests"]) == 1
    request = state["requests"][0]
    assert request.method == "GET"
    assert request.path == "/api/device/v2/getRunningCurrentDeviceMode"
    assert dict(request.query) == {
        "deviceId": "device&other=1+?#/筒",
        "bucketCode": "",
    }
    assert request.headers["token"] == "test-token"
    assert not client.command_history


async def test_idle_running_program_is_null_without_guessing_selection(service):  # noqa: F811
    client, state = service
    state["body"]["data"] = None
    assert await client.async_get_running_program("device") is None
    assert len(state["requests"]) == 1
    assert not client.command_history


@pytest.mark.parametrize(
    "data",
    [
        [],
        "private-program",
        1,
        True,
        {},
        {"id": None},
        {"id": 7},
        {"id": True},
        {"id": []},
        {"id": {}},
        {"id": ""},
        {"id": " \t"},
        {"userDeviceModeId": "private-program"},
    ],
)
async def test_invalid_running_program_shape_is_private(service, data, caplog):  # noqa: F811
    client, state = service
    state["body"]["data"] = data
    with pytest.raises(api.MinijError) as error:
        await client.async_get_running_program("private-device")
    assert len(state["requests"]) == 1
    assert "private" not in str(error.value)
    assert "private" not in caplog.text
    assert not client.command_history


@pytest.mark.parametrize("operation", ["activate", "pause", "power_off"])
async def test_cycle_command_exact_single_payload_and_private_history(
    service,  # noqa: F811
    operation,
    caplog,
):
    client, state = service
    state["body"]["data"] = None
    client._device_reports["private-device"] = {"current_status_alias": "working"}
    method = getattr(client, f"async_{operation}_program", None)
    if operation == "power_off":
        await client.async_power_off("private-device")
    else:
        await method("private-device", "private-running-program")
    expected = {
        "deviceId": "private-device",
        "bucketCode": "",
        "operateType": operation,
    }
    if operation != "power_off":
        expected["activateParam"] = {
            "userDeviceModeId": "private-running-program",
            "userDeviceModeStatsSimpleList": [],
        }
    assert state["request_body"] == expected
    assert len(state["requests"]) == 1
    request = state["requests"][0]
    assert request.method == "POST"
    assert request.path == "/api/device/v2/deviceOperate"
    assert request.headers["token"] == "test-token"
    record = client.command_history[-1]
    assert record["function"] == operation
    assert record["result"] == "accepted"
    assert record["http_status"] == 200
    assert record["before"] == {"current_status_alias": "working"}
    assert client._device_reports["private-device"] == record["before"]
    history = json.dumps(list(client.command_history))
    for secret in ("private-device", "private-running-program", "test-token"):
        assert secret not in history
        assert secret not in caplog.text


@pytest.mark.parametrize("operation", ["activate", "pause"])
@pytest.mark.parametrize(
    "device_id,program_id",
    [
        (None, "program"),
        ("", "program"),
        (" \t", "program"),
        (True, "program"),
        (1, "program"),
        ("device", None),
        ("device", ""),
        ("device", " \t"),
        ("device", 7),
        ("device", True),
    ],
)
async def test_invalid_cycle_identity_does_not_write(
    service,  # noqa: F811
    operation,
    device_id,
    program_id,
):
    client, state = service
    with pytest.raises(api.MinijError):
        await getattr(client, f"async_{operation}_program")(device_id, program_id)
    assert not state["requests"]
    assert not client.command_history


@pytest.mark.parametrize("operation", ["running_program", "power_off"])
@pytest.mark.parametrize("device_id", [None, "", " \t", True, 7])
async def test_invalid_device_identity_never_reads_or_writes(
    service,  # noqa: F811
    operation,
    device_id,
):
    client, state = service
    method = (
        client.async_get_running_program
        if operation == "running_program"
        else client.async_power_off
    )
    with pytest.raises(api.MinijError):
        await method(device_id)
    assert not state["requests"]
    assert not client.command_history


@pytest.mark.parametrize("operation", ["activate", "pause", "power_off"])
@pytest.mark.parametrize("status", [200, 401, 403, 429, 500, 302])
async def test_cycle_failures_are_typed_private_and_never_retried(
    service,  # noqa: F811
    operation,
    status,
    caplog,
):
    client, state = service
    state["status"] = status
    state["body"] = {
        "success": False,
        "errorMessage": "private-response-canary",
        "data": {"id": "private-program", "token": "private-response-token"},
    }
    expected_error = (
        api.MinijAuthError
        if status in (401, 403)
        else api.MinijRateLimitError
        if status == 429
        else api.MinijError
    )
    with pytest.raises(expected_error) as error:
        if operation == "power_off":
            await client.async_power_off("private-device")
        else:
            await getattr(client, f"async_{operation}_program")(
                "private-device", "private-program"
            )
    assert len(state["requests"]) == 1
    assert len(client.command_history) == 1
    record = client.command_history[-1]
    assert record["function"] == operation
    assert record["result"] == expected_error.__name__
    assert record["http_status"] == status
    for secret in ("private", "test-token"):
        assert secret not in str(error.value)
        assert secret not in caplog.text
        assert secret not in json.dumps(list(client.command_history))


@pytest.mark.parametrize("operation", ["activate", "pause", "power_off"])
async def test_cycle_timeout_is_one_uncertain_write_without_retry(
    service,  # noqa: F811
    operation,
    caplog,
):
    client, state = service
    with patch.object(
        client._session, "request", side_effect=TimeoutError("private-timeout")
    ) as request:
        with pytest.raises(api.MinijError) as error:
            if operation == "power_off":
                await client.async_power_off("private-device")
            else:
                await getattr(client, f"async_{operation}_program")(
                    "private-device", "private-program"
                )
    assert request.call_count == 1
    assert request.call_args.kwargs["allow_redirects"] is False
    assert request.call_args.kwargs["timeout"].total == 20
    assert len(client.command_history) == 1
    record = client.command_history[-1]
    assert record["result"] == "MinijError"
    assert record["http_status"] is None
    assert not state["requests"]
    for secret in ("private", "test-token"):
        assert secret not in str(error.value)
        assert secret not in caplog.text
        assert secret not in json.dumps(list(client.command_history))
