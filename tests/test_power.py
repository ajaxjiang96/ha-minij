"""Observed wake payload and explicit button actions using synthetic responses."""

import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from test_api import api as transport
from test_api import service  # noqa: F401
from test_homeassistant import hass  # noqa: F401

from custom_components.minij.api import MinijAuthError, MinijError, MinijRateLimitError
from custom_components.minij.button import MinijWakeButton


async def test_wake_exact_payload_single_post_and_private_ledger(service):  # noqa: F811
    client, state = service
    state["body"]["data"] = None
    client._device_reports["private-device"] = {"current_status_alias": "resting"}
    await client.async_power_on("private-device")
    assert len(state["requests"]) == 1
    request = state["requests"][0]
    assert request.path == "/api/device/v2/deviceOperate"
    assert request.method == "POST"
    assert request.headers["token"] == "test-token"
    assert state["request_body"] == {
        "deviceId": "private-device",
        "bucketCode": "",
        "operateType": "power_on",
    }
    record = client.command_history[-1]
    assert record["function"] == "power_on"
    assert record["result"] == "accepted"
    assert record["http_status"] == 200
    assert record["before"] == {"current_status_alias": "resting"}
    assert client._device_reports["private-device"] == record["before"]
    for private in ("private-device", "test-token"):
        assert private not in json.dumps(list(client.command_history))


@pytest.mark.parametrize("device_id", [None, "", 1, True])
async def test_wake_invalid_identifier_never_sends(service, device_id):  # noqa: F811
    client, state = service
    with pytest.raises(transport.MinijError):
        await client.async_power_on(device_id)
    assert state["requests"] == []
    assert not client.command_history


@pytest.mark.parametrize("status", [200, 401, 403, 429, 500, 302])
async def test_wake_rejected_or_uncertain_result_is_never_retried(
    service,  # noqa: F811
    status,
    caplog,
):
    client, state = service
    state["status"] = status
    state["body"] = {"success": False, "errorMessage": "private-response-canary"}
    with pytest.raises(transport.MinijError) as error:
        await client.async_power_on("private-device")
    assert len(state["requests"]) == 1
    record = client.command_history[-1]
    assert record["function"] == "power_on"
    assert record["result"] != "accepted"
    assert record["http_status"] == status
    for private in ("private-device", "private-response-canary", "test-token"):
        assert private not in json.dumps(list(client.command_history))
        assert private not in str(error.value)
        assert private not in caplog.text


async def test_wake_timeout_records_uncertainty_without_retry(service):  # noqa: F811
    client, state = service
    with patch.object(
        client._session, "request", side_effect=TimeoutError("private-canary")
    ) as request:
        with pytest.raises(transport.MinijError) as error:
            await client.async_power_on("private-device")
    assert request.call_count == 1
    assert "private" not in str(error.value)
    assert client.command_history[-1]["result"] == "MinijError"
    assert client.command_history[-1]["http_status"] is None


async def test_start_program_uses_observed_empty_parameter_list_without_wake(
    service,  # noqa: F811
):
    client, state = service
    state["body"]["data"] = None
    await client.async_activate_program("private-device", "private-program")
    assert len(state["requests"]) == 1
    request = state["requests"][0]
    assert request.path == "/api/device/v2/deviceOperate"
    assert request.method == "POST"
    assert request.headers["token"] == "test-token"
    assert state["request_body"] == {
        "deviceId": "private-device",
        "bucketCode": "",
        "operateType": "activate",
        "activateParam": {
            "userDeviceModeId": "private-program",
            "userDeviceModeStatsSimpleList": [],
        },
    }
    record = client.command_history[-1]
    assert record["function"] == "activate"
    assert record["result"] == "accepted"
    for private in ("private-device", "private-program", "test-token"):
        assert private not in json.dumps(list(client.command_history))


@pytest.mark.parametrize(
    "device_id,program_id",
    [
        (None, "program"),
        ("", "program"),
        ("device", None),
        ("device", ""),
        ("device", 7),
    ],
)
async def test_invalid_program_identity_never_sends(
    service,  # noqa: F811
    device_id,
    program_id,
):
    client, state = service
    with pytest.raises(transport.MinijError):
        await client.async_activate_program(device_id, program_id)
    assert state["requests"] == []
    assert not client.command_history


@pytest.mark.parametrize("status", [200, 401, 403, 429, 500, 302])
async def test_start_program_failure_never_retries_or_sends_power_on(
    service,  # noqa: F811
    status,
):
    client, state = service
    state["status"] = status
    state["body"] = {"success": False}
    with pytest.raises(transport.MinijError):
        await client.async_activate_program("device", "program")
    assert len(state["requests"]) == 1
    assert state["request_body"]["operateType"] == "activate"
    assert client.command_history[-1]["function"] == "activate"
    assert client.command_history[-1]["result"] != "accepted"


@pytest.fixture
def wake_button(hass):  # noqa: F811
    parent = SimpleNamespace(
        hass=hass,
        config_entry=SimpleNamespace(async_start_reauth=Mock()),
        client=SimpleNamespace(async_power_on=AsyncMock()),
        data={
            "synthetic-washer": {
                "deviceModel": "future-model",
                "firmwareVersion": "future-firmware",
                "deviceCharacterMap": {
                    "current_status_alias": "working",
                    "cloud_control_authorization": "close",
                },
            }
        },
        last_update_success=True,
        async_refresh=AsyncMock(),
    )
    controls = SimpleNamespace(command_lock=asyncio.Lock())
    entity = MinijWakeButton(parent, "synthetic-washer", controls)
    entity.hass = hass
    entity._active = True
    return entity


@pytest.mark.parametrize("status", ["resting", "waiting", "working", "future", None])
async def test_wake_is_enabled_without_state_firmware_or_authorization_gates(
    wake_button, status
):
    parent = wake_button.coordinator
    parent.data["synthetic-washer"]["deviceCharacterMap"]["current_status_alias"] = (
        status
    )
    before = deepcopy(parent.data)
    assert wake_button.entity_registry_enabled_default is True
    await wake_button.async_press()
    parent.async_refresh.assert_awaited_once()
    parent.client.async_power_on.assert_awaited_once_with("synthetic-washer")
    assert parent.data == before  # ACK cannot invent waiting or running state.


async def test_inactive_wake_button_does_not_even_preflight(wake_button):
    wake_button._active = False
    with pytest.raises(HomeAssistantError) as error:
        await wake_button.async_press()
    assert error.value.translation_key == "control_read_failed"
    wake_button.coordinator.async_refresh.assert_not_awaited()
    wake_button.coordinator.client.async_power_on.assert_not_awaited()


@pytest.mark.parametrize("condition", ["unloaded", "unbound", "read_failed"])
async def test_wake_rechecks_lifecycle_binding_and_read_after_preflight(
    wake_button, condition
):
    parent = wake_button.coordinator

    async def preflight():
        if condition == "unloaded":
            wake_button._active = False
        elif condition == "unbound":
            parent.data.clear()
        else:
            parent.last_update_success = False

    parent.async_refresh.side_effect = preflight
    with pytest.raises(HomeAssistantError) as error:
        await wake_button.async_press()
    assert error.value.translation_key == "control_read_failed"
    parent.client.async_power_on.assert_not_awaited()


@pytest.mark.parametrize("kind", ["auth", "rate", "uncertain"])
async def test_wake_button_errors_are_typed_private_and_single_attempt(
    wake_button, kind
):
    parent = wake_button.coordinator
    exception, translation = {
        "auth": (MinijAuthError, "control_auth_failed"),
        "rate": (MinijRateLimitError, "control_rate_limited"),
        "uncertain": (MinijError, "control_send_uncertain"),
    }[kind]
    parent.client.async_power_on.side_effect = exception("private-canary")
    with pytest.raises(HomeAssistantError) as error:
        await wake_button.async_press()
    assert error.value.translation_key == translation
    assert "private-canary" not in str(error.value)
    parent.client.async_power_on.assert_awaited_once()
    assert parent.config_entry.async_start_reauth.call_count == (kind == "auth")


async def test_wake_presses_are_serialized_and_unload_blocks_queued_press(wake_button):
    parent = wake_button.coordinator
    started, release = asyncio.Event(), asyncio.Event()

    async def command(device_id):
        started.set()
        await release.wait()

    parent.client.async_power_on.side_effect = command
    first = asyncio.create_task(wake_button.async_press())
    await started.wait()
    second = asyncio.create_task(wake_button.async_press())
    await asyncio.sleep(0)
    parent.client.async_power_on.assert_awaited_once()
    wake_button._active = False
    release.set()
    await first
    with pytest.raises(HomeAssistantError):
        await second
    parent.client.async_power_on.assert_awaited_once()
