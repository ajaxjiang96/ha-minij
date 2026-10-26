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
        patch(
            "custom_components.minij.api.MinijClient.async_get_notifications",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        with patch(
            "custom_components.minij.api.MinijClient.async_set_child_lock",
            new_callable=AsyncMock,
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


def entity_ids(hass, *, include_disabled=False):
    """Look up actual assigned entity IDs through the real registry."""
    registry = er.async_get(hass)
    return {
        entry.unique_id.removeprefix("washer-test-device_"): entry.entity_id
        for entry in registry.entities.values()
        if entry.platform == "minij" and (include_disabled or entry.disabled_by is None)
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
    assert len(ids) == 7
    expected = {
        "current_status_alias": "resting",
        "current_mode": "标准",
        "current_process": "主洗",
        "child_lock_status": "off",
        "cloud_control_authorization": "on",
        "program_remain_time": "unknown",
        "device_notification": "unknown",
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
    assert len(entity_ids(hass)) == 7


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


@pytest.mark.parametrize("source", ["reauth", "reconfigure"])
async def test_sms_reauth_preserves_registry_and_account(hass, api, sms_api, source):
    entry = await configure(hass)
    registry = er.async_get(hass)
    ids = entity_ids(hass)
    status_id = ids["current_status_alias"]
    registry.async_update_entity(status_id, name="My washer state")
    before = {e.id for e in registry.entities.values() if e.platform == "minij"}
    result = await hass.config_entries.flow.async_init(
        "minij",
        context={"source": source, "entry_id": entry.entry_id},
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
    assert result["reason"] == f"{source}_successful"
    await hass.async_block_till_done()
    assert entry.data == {"token": "sms-session-token"}
    assert entry.unique_id == "test-account"
    assert entity_ids(hass) == ids
    assert {e.id for e in registry.entities.values() if e.platform == "minij"} == before
    assert registry.async_get(status_id).name == "My washer state"


@pytest.mark.parametrize("source", ["reauth", "reconfigure"])
async def test_sms_reauth_rejects_different_account(hass, api, sms_api, source):
    entry = await configure(hass)
    api[0].return_value = {"userId": "different-account"}
    result = await hass.config_entries.flow.async_init(
        "minij",
        context={"source": source, "entry_id": entry.entry_id},
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


@pytest.mark.parametrize("language", ["en", "zh-Hans"])
async def test_authentication_translations_load_through_homeassistant(hass, language):
    """Check the exact backend resources used for menus and input labels."""
    from homeassistant.helpers.translation import async_get_translations

    strings = await async_get_translations(hass, language, "config", {"minij"})
    prefix = "component.minij.config.step."
    for step in ("user", "reauth_confirm", "reconfigure"):
        for method in ("phone", "token"):
            assert strings[f"{prefix}{step}.menu_options.{method}"].strip()
    for step, field in (("phone", "phone"), ("sms", "code"), ("token", "token")):
        assert strings[f"{prefix}{step}.title"].strip()
        assert strings[f"{prefix}{step}.description"].strip()
        assert strings[f"{prefix}{step}.data.{field}"].strip()
    assert "not supported yet" not in strings[f"{prefix}user.description"]
    assert "暂不支持" not in strings[f"{prefix}user.description"]


async def test_cloud_outage_recovery_keeps_entity_identity(hass, api):
    """An outage makes stale readings unavailable and recovery restores them."""
    from custom_components.minij.api import MinijError

    entry = await configure(hass)
    ids = entity_ids(hass)
    api[1].side_effect = MinijError("Cloud temporarily unreachable")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert not entry.runtime_data.last_update_success
    assert all(
        hass.states.get(entity_id).state == "unavailable" for entity_id in ids.values()
    )
    assert not hass.config_entries.flow.async_progress_by_handler("minij")
    api[1].side_effect = None
    changed = deepcopy(DEVICE)
    changed["deviceCharacterMap"]["current_status_alias"] = "working"
    api[1].return_value = [changed]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert entry.runtime_data.last_update_success
    assert entity_ids(hass) == ids
    assert hass.states.get(ids["current_status_alias"]).state == "working"


async def test_new_device_removal_and_return_does_not_duplicate_entities(hass, api):
    """Bind another appliance after setup, then remove and restore the first."""
    entry = await configure(hass)
    second = deepcopy(DEVICE)
    second["deviceId"] = "second-test-device"
    second["deviceNickName"] = "Second washer"
    api[1].return_value = [deepcopy(DEVICE), second]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    original_ids = {e.id for e in registry.entities.values() if e.platform == "minij"}
    assert len(original_ids) == 16
    api[1].return_value = [second]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    for entity in registry.entities.values():
        if entity.platform == "minij" and entity.disabled_by is None:
            state = hass.states.get(entity.entity_id)
            if entity.unique_id.startswith("washer-test-device_"):
                assert state.state == "unavailable"
            else:
                assert state.state != "unavailable"
    api[1].return_value = [deepcopy(DEVICE), second]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert {
        e.id for e in registry.entities.values() if e.platform == "minij"
    } == original_ids
    assert all(
        hass.states.get(e.entity_id).state != "unavailable"
        for e in registry.entities.values()
        if e.platform == "minij" and e.disabled_by is None
    )


async def test_diagnostics_allowlist_and_stale_data_marker(hass, api):
    """Nested private fields never reach diagnostics, including after an outage."""
    import json

    from custom_components.minij.api import MinijError
    from custom_components.minij.diagnostics import async_get_config_entry_diagnostics

    entry = await configure(hass)
    private = "sensitive-test-canary"
    device = deepcopy(DEVICE)
    device.update(
        {
            "deviceId": "washer-test-device",
            "deviceNickName": private,
            "token": private,
            "phone": private,
            "serial": private,
            "unknown": {"nested_private": private},
        }
    )
    device["deviceCharacterMap"]["unknown_field"] = {"secret": private}
    api[1].return_value = [device]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    calls = api[1].await_count
    result = await async_get_config_entry_diagnostics(hass, entry)
    serialized = json.dumps(result)
    for value in (private, "test-token", "test-account", "washer-test-device"):
        assert value not in serialized
    assert api[1].await_count == calls  # Download does not poll or log in.
    assert result["entry_state"] == "loaded"
    assert result["last_cloud_refresh_success"] is True
    summary = result["cached_devices"][0]
    assert summary["deviceModel"] == "minij.washer.x68"
    assert summary["reported"]["current_status_alias"] == "resting"
    assert summary["reported_online_status"] == 1
    assert summary["reported"]["program_remain_time"] == "48"
    api[1].side_effect = MinijError("Cloud outage")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    stale = await async_get_config_entry_diagnostics(hass, entry)
    assert stale["last_cloud_refresh_success"] is False
    assert stale["cached_devices"] == result["cached_devices"]
    # Removing a device removes its diagnostic record after a successful poll.
    api[1].side_effect = None
    api[1].return_value = []
    await entry.runtime_data.async_refresh()
    assert (await async_get_config_entry_diagnostics(hass, entry))[
        "cached_devices"
    ] == []


async def test_diagnostics_without_loaded_runtime(hass, api):
    """A user can inspect an unloaded entry without a live coordinator."""
    from custom_components.minij.diagnostics import async_get_config_entry_diagnostics

    entry = await configure(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["entry_state"] == "not_loaded"
    assert result["last_cloud_refresh_success"] is None
    assert result["cached_devices"] == []


async def test_metadata_refresh_preserves_user_settings_and_identity(hass, api):
    """Cloud rename/firmware changes update without reload or lost customizations."""
    from homeassistant.helpers import area_registry as ar

    entry = await configure(hass)
    ids = entity_ids(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_device_by_identifier(
        ("minij", "washer-test-device"), entry.entry_id
    )
    await ar.async_load(hass)
    area = ar.async_get(hass).async_create("Test laundry")
    registry.async_update_device(device.id, name_by_user="My washer", area_id=area.id)
    er.async_get(hass).async_update_entity(
        ids["current_status_alias"], name="My status"
    )
    old_entity_ids = {
        e.id for e in er.async_get(hass).entities.values() if e.platform == "minij"
    }
    changed = deepcopy(DEVICE)
    changed.update(
        deviceNickName="New cloud name",
        deviceModel="minij.washer.x68-reported",
        wifiVersion="test-wifi-2",
        firmwareVersion="test-firmware-2",
    )
    api[1].return_value = [changed]
    calls = api[1].await_count
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    updated = registry.async_get(device.id)
    assert updated.name == "New cloud name"
    assert updated.model == "minij.washer.x68-reported"
    assert updated.sw_version == "test-wifi-2 test-firmware-2"
    assert updated.name_by_user == "My washer"
    assert updated.area_id == area.id
    assert api[1].await_count == calls + 1
    assert entity_ids(hass) == ids
    assert {
        e.id for e in er.async_get(hass).entities.values() if e.platform == "minij"
    } == old_entity_ids
    assert er.async_get(hass).async_get(ids["current_status_alias"]).name == "My status"
    assert len(registry.devices) == 1
    # Reload must not restore the old setup snapshot or lose overrides.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(device.id).sw_version == "test-wifi-2 test-firmware-2"
    assert registry.async_get(device.id).name_by_user == "My washer"
    assert registry.async_get(device.id).area_id == area.id
    assert entity_ids(hass) == ids


async def test_status_translation_unknown_and_idle_context(hass, api):
    """Keep raw automation states and IDs, exposing idle reports as context."""
    from homeassistant.helpers.translation import async_get_translations

    entry = await configure(hass)
    ids = entity_ids(hass)
    for alias, active in (
        ("resting", False),
        ("working", True),
        ("device_exception", None),
        ("future-status", None),
        (None, None),
        ("resting", False),
    ):
        device = deepcopy(DEVICE)
        device["deviceCharacterMap"]["current_status_alias"] = alias
        api[1].return_value = [device]
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        state = hass.states.get(ids["current_status_alias"])
        assert state.state == (alias or "unknown")
        assert state.attributes["device_class"] == "enum"
        if alias:
            assert alias in state.attributes["options"]
        for key, raw in (("current_mode", "标准"), ("current_process", "主洗")):
            report = hass.states.get(ids[key])
            assert report.state == raw
            assert report.attributes["active_cycle_reported"] is active
        assert entity_ids(hass) == ids
    assert "future-status" not in state.attributes["options"]
    for language, label in (("zh-Hans", "空闲"), ("en", "Idle")):
        strings = await async_get_translations(hass, language, "entity", {"minij"})
        prefix = "component.minij.entity.sensor."
        assert strings[f"{prefix}status.state.resting"] == label
        for alias in ("working", "device_exception"):
            assert strings[f"{prefix}status.state.{alias}"]
        for key in ("reported_program", "reported_process"):
            assert strings[f"{prefix}{key}.state_attributes.active_cycle_reported.name"]


async def test_poll_backoff_rate_limit_and_reset(hass, api):
    """Bound outage retries and honor rate delays without requesting login."""
    from homeassistant.helpers.update_coordinator import UpdateFailed

    from custom_components.minij.api import MinijError, MinijRateLimitError

    entry = await configure(hass)
    coordinator = entry.runtime_data
    api[1].side_effect = MinijError("Synthetic outage")
    for delay in (60, 120, 240, 480, 900, 900):
        with pytest.raises(UpdateFailed) as error:
            await coordinator._async_update_data()
        assert error.value.retry_after == delay
    api[1].side_effect = None
    await coordinator._async_update_data()
    for error, delay in (
        (MinijRateLimitError("Limited", retry_after=1800), 1800),
        (MinijRateLimitError("Limited"), 300),
        (MinijError("Cloud failure"), 240),
    ):
        api[1].side_effect = error
        with pytest.raises(UpdateFailed) as result:
            await coordinator._async_update_data()
        assert result.value.retry_after == delay
    assert not hass.config_entries.flow.async_progress_by_handler("minij")


async def test_diagnostics_success_timestamp_survives_failure(hass, api):
    """Mark cloud fetch time, including unchanged reports, without polling on export."""
    from custom_components.minij.api import MinijError
    from custom_components.minij.diagnostics import async_get_config_entry_diagnostics

    entry = await configure(hass)
    first = await async_get_config_entry_diagnostics(hass, entry)
    timestamp = first["last_successful_cloud_refresh"]
    assert timestamp is not None
    calls = api[1].await_count
    await async_get_config_entry_diagnostics(hass, entry)
    assert api[1].await_count == calls
    api[1].side_effect = MinijError("Outage")
    await entry.runtime_data.async_refresh()
    stale = await async_get_config_entry_diagnostics(hass, entry)
    assert stale["last_successful_cloud_refresh"] == timestamp
    assert stale["last_cloud_refresh_success"] is False
    api[1].side_effect = None
    await entry.runtime_data.async_refresh()
    restored = await async_get_config_entry_diagnostics(hass, entry)
    assert restored["last_successful_cloud_refresh"] > timestamp
    assert restored["cached_devices"] == first["cached_devices"]
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert (await async_get_config_entry_diagnostics(hass, entry))[
        "last_successful_cloud_refresh"
    ] is None


@pytest.mark.parametrize(
    ("alias", "value", "expected"),
    [
        ("working", "57", "57"),
        ("working", 57, "57"),
        ("working", "0", "0"),
        ("working", "65", "65"),
        ("resting", "48", "unknown"),
        ("device_exception", "57", "unknown"),
        ("paused", "57", "unknown"),
        ("future-status", "57", "unknown"),
        (None, "57", "unknown"),
        ("working", None, "unknown"),
        ("working", "-1", "unknown"),
        ("working", -1, "unknown"),
        ("working", True, "unknown"),
        ("working", "00:57", "unknown"),
        ("working", "57.5", "unknown"),
        ("working", 57.5, "unknown"),
        ("working", "五十七", "unknown"),
    ],
)
async def test_remaining_minutes_only_for_working_v6(hass, api, alias, value, expected):
    """Expose cloud minutes only while explicitly working; zero is not completion."""
    device = deepcopy(DEVICE)
    device["deviceCharacterMap"].update(
        current_status_alias=alias, program_remain_time=value
    )
    api[1].return_value = [device]
    await configure(hass)
    state = hass.states.get(entity_ids(hass)["program_remain_time"])
    assert state.state == expected
    assert state.attributes["unit_of_measurement"] == "min"
    assert state.attributes["device_class"] == "duration"
    assert "state_class" not in state.attributes


async def test_duration_lifecycle_and_unknown_model(hass, api):
    """Idle/recovery never fabricate countdowns or completion; old IDs remain."""
    from custom_components.minij.api import MinijError

    entry = await configure(hass)
    ids = entity_ids(hass)
    remaining = ids["program_remain_time"]
    device = deepcopy(DEVICE)
    device["deviceCharacterMap"].update(
        current_status_alias="working", program_remain_time="57"
    )
    api[1].return_value = [device]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(remaining).state == "57"
    # Another successful identical report stays 57; there is no local countdown.
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(remaining).state == "57"
    api[1].side_effect = MinijError("Synthetic outage")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(remaining).state == "unavailable"
    api[1].side_effect = None
    device["deviceCharacterMap"]["current_status_alias"] = "resting"
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(remaining).state == "unknown"
    assert entity_ids(hass) == ids
    second = deepcopy(DEVICE)
    second.update(deviceId="unsupported-model-device", deviceModel="unknown-model")
    api[1].return_value = [device, second]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    entities = er.async_get(hass).entities.values()
    assert len([e for e in entities if e.platform == "minij"]) == 13
    assert not any(
        e.unique_id == "unsupported-model-device_program_remain_time" for e in entities
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert all(entity_ids(hass)[key] == value for key, value in ids.items())
    assert hass.states.get(remaining).state == "unknown"


async def test_exception_example_ignores_startup_recovery_and_repetition(hass):
    """Use the real HA state trigger: only explicit known->exception transitions."""
    from homeassistant.components.homeassistant.triggers import state
    from homeassistant.util.yaml import load_yaml

    example = load_yaml(
        str(Path(__file__).parents[1] / "examples/reported-exception.yaml")
    )
    config = await state.async_validate_trigger_config(
        hass,
        {
            "platform": "state",
            **{k: v for k, v in example["triggers"][0].items() if k != "trigger"},
        },
    )
    action = AsyncMock()
    remove = await state.async_attach_trigger(
        hass,
        config,
        action,
        {"trigger_data": {"id": "0", "idx": "0"}, "variables": {}, "name": "test"},
    )
    entity_id = config["entity_id"][0]
    try:
        for value in (
            "device_exception",  # Initial report must not notify.
            "device_exception",
            "unavailable",
            "device_exception",  # Recovery must not notify.
            "unknown",
            "device_exception",
        ):
            hass.states.async_set(entity_id, value)
            await hass.async_block_till_done()
        action.assert_not_called()
        for value in ("working", "device_exception", "device_exception"):
            hass.states.async_set(entity_id, value)
            await hass.async_block_till_done()
        assert action.call_count == 1
    finally:
        remove()


async def test_cycle_diagnostics_raw_allowlist(hass, api):
    """Retain typed protocol observations without nested or boolean payloads."""
    from custom_components.minij.diagnostics import async_get_config_entry_diagnostics

    device = deepcopy(DEVICE)
    device["deviceCharacterMap"].update(
        current_process_alias="main_wash",
        program_remain_time=57,
        program_total_time="65",
        fault_code={"private": "never-export-this"},
        arbitrary_private="never-export-this",
    )
    api[1].return_value = [device]
    entry = await configure(hass)
    calls = api[1].await_count
    result = await async_get_config_entry_diagnostics(hass, entry)
    report = result["cached_devices"][0]["reported"]
    assert report["current_process_alias"] == "main_wash"
    assert report["program_remain_time"] == 57
    assert report["program_total_time"] == "65"
    assert "fault_code" not in report
    assert "arbitrary_private" not in report
    assert api[1].await_count == calls
    device["deviceCharacterMap"].update(program_remain_time=True, fault_code="E-test")
    await entry.runtime_data.async_refresh()
    report = (await async_get_config_entry_diagnostics(hass, entry))["cached_devices"][
        0
    ]["reported"]
    assert "program_remain_time" not in report
    assert report["fault_code"] == "E-test"


async def test_completion_events_baseline_recovery_and_standard_trigger(hass, api):
    """Only new explicit messages trigger; recovery never replays stored completion."""
    from datetime import datetime, timedelta

    from homeassistant.components.event import DATA_COMPONENT
    from homeassistant.components.event.trigger import EventReceivedTrigger
    from homeassistant.helpers.trigger import TriggerConfig

    from custom_components.minij.api import DeviceNotification, MinijError

    def message(identifier, minute):
        return DeviceNotification(
            identifier,
            datetime(2026, 1, 1) + timedelta(minutes=minute),
            "wash_completed",
        )

    old = message("old", 0)
    with patch(
        "custom_components.minij.api.MinijClient.async_get_notifications",
        new_callable=AsyncMock,
        return_value=[old],
    ) as messages:
        entry = await configure(hass)
        ids = entity_ids(hass)
        event_id = ids["device_notification"]
        entity = hass.data[DATA_COMPONENT].get_entity(event_id)
        assert hass.states.get(event_id).state == "unknown"
        from homeassistant.util.yaml import load_yaml

        example = load_yaml(
            str(Path(__file__).parents[1] / "examples/program-completed.yaml")
        )
        example_trigger = dict(example["triggers"][0])
        assert example_trigger.pop("trigger") == "event.received"
        example_trigger["target"] = {"entity_id": event_id}
        config = await EventReceivedTrigger.async_validate_config(hass, example_trigger)
        trigger = EventReceivedTrigger(
            hass, TriggerConfig(key="event.received", **config)
        )
        action = AsyncMock()
        remove = await trigger.async_attach_action(action, lambda payload, _: payload)
        try:
            fresh = message("fresh", 1)
            messages.return_value = [fresh, old]
            await entity.notifications.async_refresh()
            await hass.async_block_till_done()
            assert (
                action.await_count == 1
            )  # First real event after unknown is included.
            stamp = hass.states.get(event_id).state
            assert (
                hass.states.get(event_id).attributes["event_type"] == "wash_completed"
            )
            assert "message_id" not in hass.states.get(event_id).attributes
            await entity.notifications.async_refresh()
            await hass.async_block_till_done()
            assert action.await_count == 1
            assert hass.states.get(event_id).state == stamp
            messages.side_effect = MinijError("Synthetic notification outage")
            await entity.notifications.async_refresh()
            await hass.async_block_till_done()
            assert hass.states.get(event_id).state == "unavailable"
            assert hass.states.get(ids["current_status_alias"]).state == "resting"
            messages.side_effect = None
            messages.return_value = [message("during-outage", 2), fresh, old]
            await entity.notifications.async_refresh()
            await hass.async_block_till_done()
            assert action.await_count == 1
            # The restored old event timestamp is not a new completion.
            assert hass.states.get(event_id).state == stamp
            messages.return_value.insert(0, message("after-recovery", 3))
            await entity.notifications.async_refresh()
            await hass.async_block_till_done()
            assert action.await_count == 2
            assert await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()
            assert entity_ids(hass) == ids
            assert action.await_count == 2
            # Status working->resting by itself never emits a completion event.
            for alias in ("working", "resting"):
                device = deepcopy(DEVICE)
                device["deviceCharacterMap"]["current_status_alias"] = alias
                api[1].return_value = [device]
                await entry.runtime_data.async_refresh()
                await hass.async_block_till_done()
            assert action.await_count == 2
        finally:
            remove()


@pytest.mark.parametrize("recover_before_response", [False, True])
async def test_inflight_notification_cannot_finish_reset_baseline(
    hass, api, recover_before_response
):
    """Discard a response spanning any parent outage, even if already recovered."""
    import asyncio
    from datetime import datetime, timedelta

    from homeassistant.components.event import DATA_COMPONENT

    from custom_components.minij.api import DeviceNotification, MinijError

    def message(identifier, minute):
        return DeviceNotification(
            identifier,
            datetime(2026, 1, 1) + timedelta(minutes=minute),
            "wash_completed",
        )

    old = message("old", 0)
    with patch(
        "custom_components.minij.api.MinijClient.async_get_notifications",
        new_callable=AsyncMock,
        return_value=[old],
    ) as messages:
        entry = await configure(hass)
        ids = entity_ids(hass)
        event_id = ids["device_notification"]
        entity = hass.data[DATA_COMPONENT].get_entity(event_id)
        started = asyncio.Event()
        release = asyncio.Event()

        async def delayed_response(_):
            started.set()
            await release.wait()
            return [message("inflight", 1), old]

        messages.side_effect = delayed_response
        pending = hass.async_create_task(entity.notifications.async_refresh())
        await started.wait()
        try:
            api[1].side_effect = MinijError(
                "Parent outage while notification in flight"
            )
            await entry.runtime_data.async_refresh()
            assert hass.states.get(event_id).state == "unavailable"
            if recover_before_response:
                api[1].side_effect = None
                await entry.runtime_data.async_refresh()
            release.set()
            await pending
            await hass.async_block_till_done()
            if not recover_before_response:
                api[1].side_effect = None
                await entry.runtime_data.async_refresh()
            # A stale response must not consume the recovery baseline.
            messages.side_effect = None
            messages.return_value = [
                message("during-outage", 2),
                message("inflight", 1),
                old,
            ]
            await entity.notifications.async_refresh()
            await hass.async_block_till_done()
            assert hass.states.get(event_id).state == "unknown"
            messages.return_value.insert(0, message("after-baseline", 3))
            await entity.notifications.async_refresh()
            await hass.async_block_till_done()
            assert (
                hass.states.get(event_id).attributes["event_type"] == "wash_completed"
            )
        finally:
            release.set()
            await pending


async def enable_child_lock_control(hass, entry):
    """Enable the registered experimental entity and reload like HA settings."""
    registry = er.async_get(hass)
    control_id = entity_ids(hass, include_disabled=True)["child_lock_control"]
    registry.async_update_entity(control_id, disabled_by=None)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    return control_id


async def test_child_lock_disabled_by_default_and_verified_round_trip(hass, api):
    """Loading never writes; only explicit enabled actions send one command."""
    from custom_components.minij.api import MinijClient

    command = MinijClient.async_set_child_lock
    entry = await configure(hass)
    original = entity_ids(hass)
    all_ids = entity_ids(hass, include_disabled=True)
    control_id = all_ids["child_lock_control"]
    assert er.async_get(hass).async_get(control_id).disabled_by is not None
    assert hass.states.get(control_id) is None
    command.assert_not_awaited()
    assert len(all_ids) == 8 and len(original) == 7
    await enable_child_lock_control(hass, entry)
    assert all(entity_ids(hass)[key] == value for key, value in original.items())
    assert hass.states.get(control_id).state == "off"

    async def apply_command(device_id, enabled):
        assert device_id == DEVICE["deviceId"]
        updated = deepcopy(api[1].return_value)
        updated[0]["deviceCharacterMap"]["child_lock_status"] = (
            "open" if enabled else "close"
        )
        api[1].return_value = updated

    command.side_effect = apply_command
    for action, expected in (("turn_on", "on"), ("turn_off", "off")):
        before = api[1].await_count
        await hass.services.async_call(
            "switch", action, {"entity_id": control_id}, blocking=True
        )
        await hass.async_block_till_done()
        assert hass.states.get(control_id).state == expected
        assert api[1].await_count == before + 2  # Fresh preflight and one readback.
    assert command.await_count == 2
    before = command.await_count
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": control_id}, blocking=True
    )
    assert command.await_count == before  # Already at target: no command.


@pytest.mark.parametrize(
    ("field", "value", "error_key"),
    [
        ("firmwareVersion", "unverified-firmware", "control_unsupported"),
        ("wifiVersion", None, "control_unsupported"),
        ("deviceModel", "unknown-model", "control_unsupported"),
        ("bucketCode", "other-bucket", "control_unsupported"),
        ("cloud_control_authorization", "close", "control_not_authorized"),
        ("current_status_alias", "working", "control_not_idle"),
        ("current_status_alias", "future-status", "control_not_idle"),
        ("child_lock_status", None, "control_unknown_lock"),
    ],
)
async def test_child_lock_fresh_preflight_rejects_without_writing(
    hass, api, field, value, error_key
):
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.minij.api import MinijClient

    entry = await configure(hass)
    control_id = await enable_child_lock_control(hass, entry)
    changed = deepcopy(DEVICE)
    if field in ("firmwareVersion", "wifiVersion", "deviceModel", "bucketCode"):
        changed[field] = value
    else:
        changed["deviceCharacterMap"][field] = value
    api[1].return_value = [changed]  # Cached state still looked eligible before action.
    with pytest.raises(HomeAssistantError) as result:
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": control_id}, blocking=True
        )
    assert result.value.translation_key == error_key
    MinijClient.async_set_child_lock.assert_not_awaited()


async def test_child_lock_preflight_outage_and_unconfirmed_ack(hass, api):
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.minij.api import MinijClient, MinijError

    entry = await configure(hass)
    control_id = await enable_child_lock_control(hass, entry)
    api[1].side_effect = MinijError("Synthetic outage")
    with pytest.raises(HomeAssistantError) as result:
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": control_id}, blocking=True
        )
    assert result.value.translation_key == "control_read_failed"
    MinijClient.async_set_child_lock.assert_not_awaited()
    api[1].side_effect = None
    await entry.runtime_data.async_refresh()
    with pytest.raises(HomeAssistantError) as result:
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": control_id}, blocking=True
        )
    assert result.value.translation_key == "control_not_confirmed"
    assert MinijClient.async_set_child_lock.await_count == 1
    assert hass.states.get(control_id).state == "off"  # No optimistic success.


@pytest.mark.parametrize(
    ("error_kind", "error_key"),
    [
        ("auth", "control_auth_failed"),
        ("rate", "control_rate_limited"),
        ("uncertain", "control_send_uncertain"),
    ],
)
async def test_child_lock_command_errors_do_not_retry_or_change_state(
    hass, api, error_kind, error_key
):
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.minij.api import (
        MinijAuthError,
        MinijClient,
        MinijError,
        MinijRateLimitError,
    )

    entry = await configure(hass)
    control_id = await enable_child_lock_control(hass, entry)
    errors = {
        "auth": MinijAuthError,
        "rate": MinijRateLimitError,
        "uncertain": MinijError,
    }
    MinijClient.async_set_child_lock.side_effect = errors[error_kind](
        "private-error-canary"
    )
    with pytest.raises(HomeAssistantError) as result:
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": control_id}, blocking=True
        )
    await hass.async_block_till_done()
    assert result.value.translation_key == error_key
    assert "private-error-canary" not in str(result.value)
    assert MinijClient.async_set_child_lock.await_count == 1
    assert hass.states.get(control_id).state == "off"
    flows = hass.config_entries.flow.async_progress_by_handler("minij")
    assert bool(flows) is (error_kind == "auth")


async def test_child_lock_serializes_duplicate_requests(hass, api):
    import asyncio

    from custom_components.minij.api import MinijClient

    entry = await configure(hass)
    control_id = await enable_child_lock_control(hass, entry)
    started = asyncio.Event()
    release = asyncio.Event()

    async def command(_, enabled):
        started.set()
        await release.wait()
        updated = deepcopy(api[1].return_value)
        updated[0]["deviceCharacterMap"]["child_lock_status"] = "open"
        api[1].return_value = updated

    MinijClient.async_set_child_lock.side_effect = command
    first = hass.async_create_task(
        hass.services.async_call(
            "switch", "turn_on", {"entity_id": control_id}, blocking=True
        )
    )
    await started.wait()
    second = hass.async_create_task(
        hass.services.async_call(
            "switch", "turn_on", {"entity_id": control_id}, blocking=True
        )
    )
    release.set()
    await asyncio.gather(first, second)
    await hass.async_block_till_done()
    assert MinijClient.async_set_child_lock.await_count == 1
    assert hass.states.get(control_id).state == "on"


async def test_child_lock_unload_during_preflight_never_writes(hass, api):
    import asyncio

    from homeassistant.exceptions import HomeAssistantError

    from custom_components.minij.api import MinijClient

    entry = await configure(hass)
    control_id = await enable_child_lock_control(hass, entry)
    started = asyncio.Event()
    release = asyncio.Event()

    async def delayed_read():
        started.set()
        await release.wait()
        return [deepcopy(DEVICE)]

    api[1].side_effect = delayed_read
    pending = hass.async_create_task(
        hass.services.async_call(
            "switch", "turn_on", {"entity_id": control_id}, blocking=True
        )
    )
    await started.wait()
    try:
        assert await hass.config_entries.async_unload(entry.entry_id)
        release.set()
        with pytest.raises(HomeAssistantError) as result:
            await pending
        assert result.value.translation_key == "control_read_failed"
        MinijClient.async_set_child_lock.assert_not_awaited()
    finally:
        release.set()


@pytest.mark.parametrize("language", ["en", "zh-Hans"])
async def test_child_lock_exception_and_entity_translations(hass, language):
    from homeassistant.helpers.translation import async_get_translations

    entities = await async_get_translations(hass, language, "entity", {"minij"})
    assert entities["component.minij.entity.switch.child_lock_control.name"]
    exceptions = await async_get_translations(hass, language, "exceptions", {"minij"})
    for key in (
        "control_read_failed",
        "control_unsupported",
        "control_not_authorized",
        "control_not_idle",
        "control_unknown_lock",
        "control_auth_failed",
        "control_rate_limited",
        "control_send_uncertain",
        "control_not_confirmed",
    ):
        assert exceptions[f"component.minij.exceptions.{key}.message"]
