"""Pause/resume actual-running identity and shared explicit command behavior."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.exceptions import HomeAssistantError
from test_homeassistant import hass  # noqa: F401

from custom_components.minij.api import MinijAuthError, MinijError, MinijRateLimitError
from custom_components.minij.button import (
    MinijPauseButton,
    MinijPowerOffButton,
    MinijResumeButton,
)

BUTTONS = {
    "pause": MinijPauseButton,
    "resume": MinijResumeButton,
    "power_off": MinijPowerOffButton,
}
OPERATIONS = {
    "pause": "async_pause_program",
    "resume": "async_activate_program",
    "power_off": "async_power_off",
}


@pytest.fixture
def cycle_context(hass):  # noqa: F811
    parent = SimpleNamespace(
        hass=hass,
        config_entry=SimpleNamespace(async_start_reauth=Mock()),
        client=SimpleNamespace(
            async_get_running_program=AsyncMock(return_value="actual-running-id"),
            async_pause_program=AsyncMock(),
            async_activate_program=AsyncMock(),
            async_power_off=AsyncMock(),
            async_power_on=AsyncMock(),
        ),
        data={
            "synthetic-washer": {
                "deviceModel": "future-model",
                "firmwareVersion": "future-firmware",
                "deviceCharacterMap": {
                    "current_status_alias": "future-state",
                    "cloud_control_authorization": "close",
                },
            }
        },
        last_update_success=True,
        async_refresh=AsyncMock(),
    )
    controls = SimpleNamespace(
        command_lock=asyncio.Lock(),
        data=SimpleNamespace(current_id="different-local-draft"),
        last_update_success=False,
        async_refresh=AsyncMock(side_effect=AssertionError("Unrelated catalog read")),
    )
    return parent, controls


def button_for(context, kind):
    parent, controls = context
    entity = BUTTONS[kind](parent, "synthetic-washer", controls)
    entity.hass = parent.hass
    entity._active = True
    return entity


@pytest.mark.parametrize("kind", BUTTONS)
@pytest.mark.parametrize("status", [None, "resting", "waiting", "working", "future"])
async def test_cycle_actions_have_no_state_firmware_or_catalog_gates(
    cycle_context, kind, status
):
    parent, controls = cycle_context
    parent.data["synthetic-washer"]["deviceCharacterMap"]["current_status_alias"] = (
        status
    )
    before = deepcopy(parent.data)
    entity = button_for(cycle_context, kind)
    assert entity.entity_registry_enabled_default is True
    await entity.async_press()
    parent.async_refresh.assert_awaited_once()
    controls.async_refresh.assert_not_awaited()
    operation = getattr(parent.client, OPERATIONS[kind])
    operation.assert_awaited_once_with(
        "synthetic-washer", *(["actual-running-id"] if kind != "power_off" else [])
    )
    assert parent.client.async_get_running_program.await_count == (kind != "power_off")
    for other_kind, name in OPERATIONS.items():
        if other_kind != kind:
            getattr(parent.client, name).assert_not_awaited()
    parent.client.async_power_on.assert_not_awaited()
    assert parent.data == before
    assert controls.data.current_id == "different-local-draft"


async def test_power_off_does_not_need_any_running_program_or_catalog(cycle_context):
    parent, controls = cycle_context
    controls.data = None
    parent.client.async_get_running_program.side_effect = AssertionError(
        "Power off must not depend on running identity"
    )
    await button_for(cycle_context, "power_off").async_press()
    parent.client.async_power_off.assert_awaited_once_with("synthetic-washer")
    parent.client.async_get_running_program.assert_not_awaited()
    controls.async_refresh.assert_not_awaited()


@pytest.mark.parametrize("kind", ["pause", "resume"])
@pytest.mark.parametrize("identifier", [None, "", " ", 1, True, {}])
async def test_no_valid_running_id_never_uses_local_draft(
    cycle_context, kind, identifier
):
    parent, _ = cycle_context
    parent.client.async_get_running_program.return_value = identifier
    with pytest.raises(HomeAssistantError) as error:
        await button_for(cycle_context, kind).async_press()
    assert error.value.translation_key == "control_no_running_program"
    parent.client.async_get_running_program.assert_awaited_once()
    for name in OPERATIONS.values():
        getattr(parent.client, name).assert_not_awaited()


@pytest.mark.parametrize("kind", BUTTONS)
async def test_inactive_cycle_button_never_reads_or_sends(cycle_context, kind):
    parent, _ = cycle_context
    entity = button_for(cycle_context, kind)
    entity._active = False
    with pytest.raises(HomeAssistantError) as error:
        await entity.async_press()
    assert error.value.translation_key == "control_read_failed"
    parent.async_refresh.assert_not_awaited()
    parent.client.async_get_running_program.assert_not_awaited()
    for name in OPERATIONS.values():
        getattr(parent.client, name).assert_not_awaited()


@pytest.mark.parametrize("kind", BUTTONS)
@pytest.mark.parametrize("change", ["unloaded", "unbound", "read_failed"])
async def test_cycle_preflight_rechecks_lifecycle_and_binding(
    cycle_context, kind, change
):
    parent, _ = cycle_context
    entity = button_for(cycle_context, kind)

    async def changed():
        if change == "unloaded":
            entity._active = False
        elif change == "unbound":
            parent.data.clear()
        else:
            parent.last_update_success = False

    parent.async_refresh.side_effect = changed
    with pytest.raises(HomeAssistantError) as error:
        await entity.async_press()
    assert error.value.translation_key == "control_read_failed"
    parent.client.async_get_running_program.assert_not_awaited()
    for name in OPERATIONS.values():
        getattr(parent.client, name).assert_not_awaited()


@pytest.mark.parametrize("kind", ["pause", "resume"])
@pytest.mark.parametrize("change", ["unloaded", "unbound", "read_failed"])
async def test_running_program_read_rechecks_lifecycle_before_write(
    cycle_context, kind, change
):
    parent, _ = cycle_context
    entity = button_for(cycle_context, kind)

    async def changed(device_id):
        if change == "unloaded":
            entity._active = False
        elif change == "unbound":
            parent.data.clear()
        else:
            parent.last_update_success = False
        return "actual-running-id"

    parent.client.async_get_running_program.side_effect = changed
    with pytest.raises(HomeAssistantError) as error:
        await entity.async_press()
    assert error.value.translation_key == "control_read_failed"
    for name in OPERATIONS.values():
        getattr(parent.client, name).assert_not_awaited()


@pytest.mark.parametrize("kind", ["pause", "resume"])
@pytest.mark.parametrize("failure", ["auth", "rate", "connection"])
async def test_running_program_read_failure_never_writes_or_retries(
    cycle_context, kind, failure
):
    parent, _ = cycle_context
    exception, translation = {
        "auth": (MinijAuthError, "control_auth_failed"),
        "rate": (MinijRateLimitError, "control_rate_limited"),
        "connection": (MinijError, "control_read_failed"),
    }[failure]
    parent.client.async_get_running_program.side_effect = exception("private-canary")
    with pytest.raises(HomeAssistantError) as error:
        await button_for(cycle_context, kind).async_press()
    assert error.value.translation_key == translation
    assert "private-canary" not in str(error.value)
    parent.client.async_get_running_program.assert_awaited_once()
    for name in OPERATIONS.values():
        getattr(parent.client, name).assert_not_awaited()
    assert parent.config_entry.async_start_reauth.call_count == (failure == "auth")


@pytest.mark.parametrize("kind", BUTTONS)
@pytest.mark.parametrize("failure", ["auth", "rate", "uncertain"])
async def test_cycle_write_failure_is_one_private_attempt(cycle_context, kind, failure):
    parent, _ = cycle_context
    exception, translation = {
        "auth": (MinijAuthError, "control_auth_failed"),
        "rate": (MinijRateLimitError, "control_rate_limited"),
        "uncertain": (MinijError, "control_send_uncertain"),
    }[failure]
    command = getattr(parent.client, OPERATIONS[kind])
    command.side_effect = exception("private-canary")
    before = deepcopy(parent.data)
    with pytest.raises(HomeAssistantError) as error:
        await button_for(cycle_context, kind).async_press()
    assert error.value.translation_key == translation
    assert "private-canary" not in str(error.value)
    command.assert_awaited_once()
    parent.client.async_power_on.assert_not_awaited()
    assert parent.config_entry.async_start_reauth.call_count == (failure == "auth")
    assert parent.data == before


async def test_cycle_buttons_share_lock_and_unload_blocks_queued_write(cycle_context):
    parent, _ = cycle_context
    pause = button_for(cycle_context, "pause")
    power_off = button_for(cycle_context, "power_off")
    started, release = asyncio.Event(), asyncio.Event()

    async def delayed(*args):
        started.set()
        await release.wait()

    parent.client.async_pause_program.side_effect = delayed
    first = asyncio.create_task(pause.async_press())
    await started.wait()
    second = asyncio.create_task(power_off.async_press())
    await asyncio.sleep(0)
    parent.async_refresh.assert_awaited_once()
    parent.client.async_power_off.assert_not_awaited()
    power_off._active = False
    release.set()
    await first
    with pytest.raises(HomeAssistantError) as error:
        await second
    assert error.value.translation_key == "control_read_failed"
    parent.client.async_pause_program.assert_awaited_once()
    parent.client.async_power_off.assert_not_awaited()
