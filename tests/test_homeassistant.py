"""Exercise the integration through a real Home Assistant runtime."""

from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant import loader
from homeassistant.config_entries import ConfigEntries, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import frame

from custom_components.minij.api import MinijAuthError

DEVICE = {
    "deviceId": "washer-test-device",
    "deviceType": "washer",
    "deviceName": "Test washer",
    "deviceNickName": "Laundry washer",
    "deviceModel": "minij.washer.x68",
    "firmwareVersion": "0 0003 1 0000",
    "wifiVersion": "1.0253",
    "newOrOldAppOnlineStatus": 1,
    "deviceCharacterMap": {
        "current_status_alias": "resting",
        "current_status": "休息中",
        "current_mode": "标准",
        "current_process": "主洗",
        "child_lock_status": "close",
        "cloud_control_authorization": "open",
        "program_remain_time": "48",
    },
}


@pytest.fixture
async def hass(tmp_path):
    """Initialize real HA managers and load the local custom component."""
    (tmp_path / "custom_components").symlink_to(
        Path(__file__).resolve().parents[1] / "custom_components",
        target_is_directory=True,
    )
    instance = HomeAssistant(str(tmp_path))
    frame.async_setup(instance)
    loader.async_setup(instance)
    instance.config_entries = ConfigEntries(instance, {})
    await instance.config_entries.async_initialize()
    dr.async_setup(instance)
    await dr.async_load(instance)
    await er.async_load(instance)
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
    ) as session:
        with (
            patch(
                "custom_components.minij.async_get_clientsession", return_value=session
            ),
            patch(
                "custom_components.minij.config_flow.async_get_clientsession",
                return_value=session,
            ),
        ):
            try:
                yield instance
            finally:
                await instance.async_stop(force=True)
                await instance.async_block_till_done()
                frame._hass.hass = None


@pytest.fixture
def api():
    """Mock only the external MiniJ API, preserving all HA code paths."""
    with (
        patch(
            "custom_components.minij.api.MinijClient.async_get_profile",
            new_callable=AsyncMock,
            return_value={"userId": "test-account"},
        ) as profile,
        patch(
            "custom_components.minij.api.MinijClient.async_get_devices",
            new_callable=AsyncMock,
            return_value=[deepcopy(DEVICE)],
        ) as devices,
    ):
        yield profile, devices


async def configure(hass):
    """Create and set up a config entry using the real flow manager."""
    result = await hass.config_entries.flow.async_init(
        "minij", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "token"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"token": " test-token "}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state == ConfigEntryState.LOADED
    return entry


def entity_ids(hass):
    """Look up actual assigned entity IDs through the real registry."""
    registry = er.async_get(hass)
    return {
        entry.unique_id.removeprefix("washer-test-device_"): entry.entity_id
        for entry in registry.entities.values()
        if entry.platform == "minij"
    }


async def test_config_flow_entities_and_unload(hass, api):
    """Configure, poll once for all entities, and unload cleanly."""
    profile, devices = api
    entry = await configure(hass)
    assert entry.unique_id == "test-account"
    assert entry.data == {"token": "test-token"}
    assert profile.await_count == 1
    assert devices.await_count == 2  # Flow validation and one coordinator refresh.

    ids = entity_ids(hass)
    assert len(ids) == 5
    expected = {
        "current_status_alias": "resting",
        "current_mode": "标准",
        "current_process": "主洗",
        "child_lock_status": "off",
        "cloud_control_authorization": "on",
    }
    for key, value in expected.items():
        state = hass.states.get(ids[key])
        assert state is not None
        assert state.state == value
        assert "token" not in state.attributes
    assert (
        hass.states.get(ids["current_status_alias"]).attributes["reported_status"]
        == "休息中"
    )

    device = dr.async_get(hass).async_get_device_by_identifier(
        ("minij", "washer-test-device"), entry.entry_id
    )
    assert device is not None
    assert device.name == "Laundry washer"
    assert device.model == "minij.washer.x68"
    assert device.sw_version == "1.0253 0 0003 1 0000"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.NOT_LOADED
    assert all(
        hass.states.get(entity_id).state == "unavailable" for entity_id in ids.values()
    )


async def test_shared_refresh_unknown_values_and_removed_device(hass, api):
    """Unknown binary fields stay unknown and removed devices become unavailable."""
    _, devices = api
    entry = await configure(hass)
    ids = entity_ids(hass)
    changed = deepcopy(DEVICE)
    changed["deviceCharacterMap"]["current_status_alias"] = "future-status"
    changed["deviceCharacterMap"]["child_lock_status"] = "future-value"
    changed["deviceCharacterMap"].pop("cloud_control_authorization")
    devices.return_value = [changed]
    calls = devices.await_count
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert devices.await_count == calls + 1
    assert hass.states.get(ids["current_status_alias"]).state == "future-status"
    assert hass.states.get(ids["child_lock_status"]).state == "unknown"
    assert hass.states.get(ids["cloud_control_authorization"]).state == "unknown"
    devices.return_value = []
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert all(
        hass.states.get(entity_id).state == "unavailable" for entity_id in ids.values()
    )


async def test_auth_failure_starts_reauth_and_rejects_wrong_account(hass, api):
    """An expired token starts reauth, which must preserve the original account."""
    profile, devices = api
    entry = await configure(hass)
    ids = entity_ids(hass)
    devices.side_effect = MinijAuthError("Expired test session")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert all(
        hass.states.get(entity_id).state == "unavailable" for entity_id in ids.values()
    )
    flows = hass.config_entries.flow.async_progress_by_handler("minij")
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"
    devices.side_effect = None
    profile.return_value = {"userId": "different-account"}
    result = await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], {"next_step_id": "token"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"token": "wrong-account-token"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert entry.data["token"] == "test-token"
    profile.return_value = {"userId": "test-account"}
    result = await hass.config_entries.flow.async_init(
        "minij",
        context={"source": "reauth", "entry_id": entry.entry_id},
        data=entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "token"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"token": "replacement-token"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert entry.data["token"] == "replacement-token"
    assert entry.state == ConfigEntryState.LOADED
    assert hass.states.get(ids["current_status_alias"]).state == "resting"


async def test_duplicate_account_is_not_created(hass, api):
    """A second session for the same account does not duplicate entities."""
    await configure(hass)
    result = await hass.config_entries.flow.async_init(
        "minij", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "token"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"token": "another-test-token"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries("minij")) == 1


@pytest.fixture
def sms_api():
    """Mock only the two external authentication operations."""
    with (
        patch(
            "custom_components.minij.api.MinijClient.async_request_sms",
            new_callable=AsyncMock,
        ) as send,
        patch(
            "custom_components.minij.api.MinijClient.async_login",
            new_callable=AsyncMock,
            return_value="sms-session-token",
        ) as login,
    ):
        yield send, login


async def open_sms(hass):
    result = await hass.config_entries.flow.async_init(
        "minij", context={"source": "user"}
    )
    assert result["type"] == FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "phone"}
    )


async def test_sms_requires_submission_and_stores_only_token(hass, api, sms_api):
    send, login = sms_api
    result = await open_sms(hass)
    assert result["step_id"] == "phone"
    send.assert_not_awaited()
    login.assert_not_awaited()
    # Redisplaying a form cannot send an SMS.
    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    send.assert_not_awaited()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"phone": " 13800000000 "}
    )
    assert result["step_id"] == "sms"
    send.assert_awaited_once_with("13800000000")
    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    send.assert_awaited_once()
    login.assert_not_awaited()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"code": " 001234 "}
    )
    login.assert_awaited_once_with("13800000000", "001234")
    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.data == {"token": "sms-session-token"}
    assert entry.unique_id == "test-account"
    await hass.async_block_till_done()
    assert len(entity_ids(hass)) == 5


@pytest.mark.parametrize(
    "phone", ["", "+8613800000000", "1380000000", "abc", "２３８００００００００"]
)
async def test_invalid_phone_does_not_send(hass, api, sms_api, phone):
    send, _ = sms_api
    result = await open_sms(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"phone": phone}
    )
    assert result["errors"] == {"phone": "invalid_phone"}
    send.assert_not_awaited()


@pytest.mark.parametrize(
    ("operation", "exception", "error"),
    [
        ("send", "rate", "rate_limited"),
        ("send", "login", "sms_rejected"),
        ("send", "network", "sms_uncertain"),
        ("login", "rate", "rate_limited"),
        ("login", "login", "login_rejected"),
        ("login", "network", "login_uncertain"),
    ],
)
async def test_auth_errors_never_retry_automatically(
    hass, api, sms_api, operation, exception, error
):
    from custom_components.minij.api import (
        MinijError,
        MinijLoginError,
        MinijRateLimitError,
    )

    send, login = sms_api
    failures = {
        "rate": MinijRateLimitError,
        "login": MinijLoginError,
        "network": MinijError,
    }
    target = send if operation == "send" else login
    target.side_effect = failures[exception]("private-server-detail")
    result = await open_sms(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"phone": "13800000000"}
    )
    if operation == "login":
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "001234"}
        )
    assert result["errors"] == {"base": error}
    assert target.await_count == 1
    assert "private-server-detail" not in str(result)
    assert len(hass.config_entries.async_entries("minij")) == 0


async def test_read_retry_does_not_exchange_code_twice(hass, api, sms_api):
    from custom_components.minij.api import MinijError

    profile, _ = api
    send, login = sms_api
    profile.side_effect = MinijError("Temporary outage after successful login")
    result = await open_sms(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"phone": "13800000000"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"code": "001234"}
    )
    assert result["step_id"] == "validate"
    assert result["errors"] == {"base": "cannot_connect"}
    profile.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    send.assert_awaited_once()
    login.assert_awaited_once()
    await hass.async_block_till_done()


async def test_sms_reauth_preserves_registry_and_account(hass, api, sms_api):
    entry = await configure(hass)
    registry = er.async_get(hass)
    ids = entity_ids(hass)
    status_id = ids["current_status_alias"]
    registry.async_update_entity(status_id, name="My washer state")
    before = {e.id for e in registry.entities.values() if e.platform == "minij"}
    result = await hass.config_entries.flow.async_init(
        "minij",
        context={"source": "reauth", "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] == FlowResultType.MENU
    sms_api[0].assert_not_awaited()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "phone"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"phone": "13800000000"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"code": "001234"}
    )
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert entry.data == {"token": "sms-session-token"}
    assert entry.unique_id == "test-account"
    assert entity_ids(hass) == ids
    assert {e.id for e in registry.entities.values() if e.platform == "minij"} == before
    assert registry.async_get(status_id).name == "My washer state"


async def test_sms_reauth_rejects_different_account(hass, api, sms_api):
    entry = await configure(hass)
    api[0].return_value = {"userId": "different-account"}
    result = await hass.config_entries.flow.async_init(
        "minij",
        context={"source": "reauth", "entry_id": entry.entry_id},
        data=entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "phone"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"phone": "13800000000"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"code": "001234"}
    )
    assert result["reason"] == "wrong_account"
    assert entry.data == {"token": "test-token"}


async def test_invalid_code_and_cancel_do_not_send_more_sms(hass, api, sms_api):
    result = await open_sms(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"phone": "13800000000"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"code": "not-a-code"}
    )
    assert result["errors"] == {"code": "invalid_code"}
    hass.config_entries.flow.async_abort(result["flow_id"])
    sms_api[0].assert_awaited_once()
    sms_api[1].assert_not_awaited()
    assert not hass.config_entries.async_entries("minij")


async def test_sms_duplicate_account_and_no_devices(hass, api, sms_api):
    await configure(hass)
    api[1].return_value = []
    result = await open_sms(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"phone": "13800000000"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"code": "001234"}
    )
    assert result["step_id"] == "validate"
    assert result["errors"] == {"base": "no_devices"}
    api[1].return_value = [deepcopy(DEVICE)]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries("minij")) == 1
    sms_api[1].assert_awaited_once()


async def test_rejected_new_session_aborts_without_retry(hass, api, sms_api):
    api[0].side_effect = MinijAuthError("Rejected new token")
    result = await open_sms(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"phone": "13800000000"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"code": "001234"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "invalid_auth"
    assert len(hass.config_entries.async_entries("minij")) == 0
    sms_api[0].assert_awaited_once()
    sms_api[1].assert_awaited_once()
