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
        "minij", context={"source": "user"}, data={"token": " test-token "}
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
        flows[0]["flow_id"], {"token": "wrong-account-token"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "wrong_account"}
    assert entry.data["token"] == "test-token"
    profile.return_value = {"userId": "test-account"}
    result = await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], {"token": "replacement-token"}
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
        "minij", context={"source": "user"}, data={"token": "another-test-token"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries("minij")) == 1
