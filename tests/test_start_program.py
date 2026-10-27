"""Explicit pending-program start using synthetic shared program metadata."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.exceptions import HomeAssistantError
from test_homeassistant import hass  # noqa: F401
from test_programs import (
    PROGRAM_A,
    PROGRAM_B,
    parameters,
    programs,
)
from test_programs import controls as program_controls  # noqa: F401

from custom_components.minij.api import MinijAuthError, MinijError, MinijRateLimitError
from custom_components.minij.button import MinijStartProgramButton


@pytest.fixture
def start_button(program_controls):  # noqa: F811
    controls = program_controls
    controls.parent.client.async_activate_program = AsyncMock()
    controls.parent.client.async_power_on = AsyncMock()
    entity = MinijStartProgramButton(controls.parent, controls.device_id, controls)
    entity.hass = controls.hass
    entity._active = True
    return entity


async def test_start_program_preflights_once_without_wake_or_optimistic_state(
    start_button,
):
    controls = start_button.controls
    client = controls.parent.client
    before = deepcopy(controls.parent.data)
    before_programs = controls.data
    reads = client.async_get_program_parameters.await_count
    assert start_button.entity_registry_enabled_default is True
    await start_button.async_press()
    client.async_activate_program.assert_awaited_once_with(
        "synthetic-washer", PROGRAM_A["id"]
    )
    controls.parent.async_refresh.assert_awaited_once()
    assert client.async_get_program_parameters.await_count == reads + 1
    client.async_power_on.assert_not_awaited()
    assert controls.parent.data == before
    assert controls.data == before_programs


async def test_start_uses_local_draft_instead_of_old_cloud_catalog(start_button):
    controls = start_button.controls
    await controls.async_select_draft(PROGRAM_B["id"])
    await start_button.async_press()
    controls.parent.client.async_activate_program.assert_awaited_once_with(
        "synthetic-washer", PROGRAM_B["id"]
    )
    assert controls.data.cloud_catalog_current_id == PROGRAM_A["id"]
    assert controls.data.current_id == PROGRAM_B["id"]
    assert controls.data.selection_source == "local_draft"


async def test_start_rejects_program_change_while_waiting_for_shared_lock(start_button):
    controls = start_button.controls
    await controls.command_lock.acquire()
    task = asyncio.create_task(start_button.async_press())
    await asyncio.sleep(0)
    await controls.async_select_draft(PROGRAM_B["id"])
    controls.command_lock.release()
    with pytest.raises(HomeAssistantError) as error:
        await task
    assert error.value.translation_key == "program_changed"
    controls.parent.client.async_activate_program.assert_not_awaited()
    controls.parent.client.async_power_on.assert_not_awaited()


async def test_start_rejects_program_changed_by_fresh_metadata(start_button):
    controls = start_button.controls
    controls.parent.client.async_get_programs.return_value = programs(PROGRAM_B)
    with pytest.raises(HomeAssistantError) as error:
        await start_button.async_press()
    assert error.value.translation_key == "program_changed"
    controls.parent.client.async_activate_program.assert_not_awaited()


async def test_start_requires_a_current_program_without_inventing_one(start_button):
    controls = start_button.controls
    controls.parent.client.async_get_programs.return_value = programs(None)
    await controls.async_refresh()
    with pytest.raises(HomeAssistantError) as error:
        await start_button.async_press()
    assert error.value.translation_key == "program_option_unavailable"
    controls.parent.client.async_activate_program.assert_not_awaited()


async def test_inactive_start_does_not_read_or_send(start_button):
    start_button._active = False
    start_button.controls.parent.async_refresh.reset_mock()
    with pytest.raises(HomeAssistantError) as error:
        await start_button.async_press()
    assert error.value.translation_key == "control_read_failed"
    start_button.controls.parent.async_refresh.assert_not_awaited()
    start_button.controls.parent.client.async_activate_program.assert_not_awaited()


async def test_start_unloaded_during_metadata_read_does_not_send(start_button):
    controls = start_button.controls

    async def unloaded(*args):
        start_button._active = False
        return parameters()

    controls.parent.client.async_get_program_parameters.side_effect = unloaded
    with pytest.raises(HomeAssistantError) as error:
        await start_button.async_press()
    assert error.value.translation_key == "control_read_failed"
    controls.parent.client.async_activate_program.assert_not_awaited()


@pytest.mark.parametrize("kind", ["auth", "rate", "uncertain"])
async def test_start_failure_is_private_and_never_retried(start_button, kind):
    controls = start_button.controls
    controls.parent.config_entry = SimpleNamespace(async_start_reauth=Mock())
    exception, translation = {
        "auth": (MinijAuthError, "control_auth_failed"),
        "rate": (MinijRateLimitError, "control_rate_limited"),
        "uncertain": (MinijError, "control_send_uncertain"),
    }[kind]
    controls.parent.client.async_activate_program.side_effect = exception(
        "private-canary"
    )
    with pytest.raises(HomeAssistantError) as error:
        await start_button.async_press()
    assert error.value.translation_key == translation
    assert "private-canary" not in str(error.value)
    controls.parent.client.async_activate_program.assert_awaited_once()
    controls.parent.client.async_power_on.assert_not_awaited()
    assert controls.parent.config_entry.async_start_reauth.call_count == (
        kind == "auth"
    )
