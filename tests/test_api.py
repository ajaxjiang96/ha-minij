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

    @routes.get("/api/{route:.*}")
    async def handle(request):
        state["requests"].append(request)
        return web.json_response(state["body"], status=state["status"])

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
