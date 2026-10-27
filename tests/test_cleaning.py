"""Cleaning-page metadata and explicit actions with synthetic cloud responses."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from test_homeassistant import hass  # noqa: F401

from custom_components.minij.api import MinijAuthError, MinijError, MinijRateLimitError
from custom_components.minij.button import MinijStartCleaningButton
from custom_components.minij.cleaning import MinijCleaningCoordinator, parse_cleaning
from custom_components.minij.select import MinijCleaningThresholdSelect
from custom_components.minij.switch import MinijCleaningSwitch

METADATA = {
    "deviceModeId": None,
    "intelligentBucketCleanTrusteeship": None,
    "intelligentBucketCleanRemind": True,
    "bucketCleanRemindBeforeTimes": 40,
    "alreadyCleanTimes": 1,
    "optionalValueList": [
        {"label": "20次", "value": 20},
        {"label": "40次", "value": 40},
    ],
}


@pytest.fixture
async def controls(hass):  # noqa: F811
    client = SimpleNamespace(
        async_get_cleaning=AsyncMock(return_value=deepcopy(METADATA)),
        async_set_cleaning_switch=AsyncMock(),
        async_set_cleaning_threshold=AsyncMock(),
        async_start_cleaning=AsyncMock(),
    )
    parent = SimpleNamespace(
        hass=hass,
        config_entry=None,
        client=client,
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
    controls = MinijCleaningCoordinator(parent, "synthetic-washer")
    await controls.async_refresh()
    return controls


def entity_for(controls, kind="reminder"):
    if kind == "button":
        entity = MinijStartCleaningButton(controls.parent, controls.device_id, controls)
    elif kind == "threshold":
        entity = MinijCleaningThresholdSelect(
            controls.parent, controls.device_id, controls
        )
    else:
        entity = MinijCleaningSwitch(
            controls.parent, controls.device_id, controls, f"cleaning_{kind}"
        )
    entity.hass = controls.hass
    entity._active = True
    return entity


def test_cleaning_parser_does_not_treat_menu_or_null_as_boolean():
    state = parse_cleaning({**METADATA, "private": "private-canary"})
    assert state.trusteeship is None
    assert state.reminder is True
    assert state.threshold == 40
    assert state.mode_id is None
    assert state.options == (("20次", 20), ("40次", 40))
    assert "private-canary" not in repr(state)


@pytest.mark.parametrize(
    "choices",
    [
        None,
        {},
        [None],
        [{"label": "20次", "value": "20"}],
        [{"label": "20次", "value": True}],
        [{"label": "20次", "value": 20}] * 2,
    ],
)
def test_cleaning_parser_rejects_ambiguous_or_invalid_options(choices):
    with pytest.raises(MinijError):
        parse_cleaning({**METADATA, "optionalValueList": choices})


async def test_cleaning_diagnostics_omit_identifiers(controls):
    raw = deepcopy(METADATA)
    raw.update(
        deviceId="private-device", deviceModeId="private-mode", userId="private-account"
    )
    controls.parent.client.async_get_cleaning.return_value = raw
    await controls.async_refresh()
    snapshot = controls.diagnostics_snapshot()
    assert snapshot["reminder"] is True
    assert snapshot["reminder_options"] == [20, 40]
    assert "private" not in repr(snapshot)


@pytest.mark.parametrize(
    "trusteeship,expected",
    [
        (None, "canSelfCleaningReminder"),
        (False, "canSelfCleaningReminder"),
        (True, "intelligentSelfCleanStartRemindSwitch"),
    ],
)
async def test_cleaning_reminder_uses_fresh_trusteeship_specific_code(
    controls, trusteeship, expected
):
    entity = entity_for(controls)
    client = controls.parent.client
    client.async_get_cleaning.return_value["intelligentBucketCleanTrusteeship"] = (
        trusteeship
    )

    async def command(device_id, code, enabled):
        client.async_get_cleaning.return_value["intelligentBucketCleanRemind"] = enabled

    client.async_set_cleaning_switch.side_effect = command
    await entity.async_turn_off()
    client.async_set_cleaning_switch.assert_awaited_once_with(
        "synthetic-washer", expected, False
    )
    assert entity.is_on is False


async def test_cleaning_trusteeship_requires_current_non_null_capability(controls):
    entity = entity_for(controls, "trusteeship")
    with pytest.raises(HomeAssistantError) as err:
        await entity.async_turn_on()
    assert err.value.translation_key == "cleaning_setting_unavailable"
    controls.parent.client.async_set_cleaning_switch.assert_not_awaited()
    client = controls.parent.client
    client.async_get_cleaning.return_value["intelligentBucketCleanTrusteeship"] = False

    async def command(device_id, code, enabled):
        client.async_get_cleaning.return_value["intelligentBucketCleanTrusteeship"] = (
            enabled
        )

    client.async_set_cleaning_switch.side_effect = command
    await entity.async_turn_on()
    client.async_set_cleaning_switch.assert_awaited_once_with(
        "synthetic-washer", "intelligentSelfCleanTrusteeship", True
    )
    assert entity.is_on is True


async def test_cleaning_threshold_uses_metadata_values_and_no_op(controls):
    entity = entity_for(controls, "threshold")
    client = controls.parent.client
    assert entity.options == ["20次", "40次"]
    assert entity.current_option == "40次"
    await entity.async_select_option("40次")
    client.async_set_cleaning_threshold.assert_not_awaited()

    async def command(device_id, value):
        client.async_get_cleaning.return_value["bucketCleanRemindBeforeTimes"] = value

    client.async_set_cleaning_threshold.side_effect = command
    await entity.async_select_option("20次")
    client.async_set_cleaning_threshold.assert_awaited_once_with("synthetic-washer", 20)
    assert entity.current_option == "20次"
    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("999次")
    assert client.async_set_cleaning_threshold.await_count == 1


async def test_cleaning_button_sends_null_mode_once_without_inventing_execution(
    controls,
):
    entity = entity_for(controls, "button")
    client = controls.parent.client
    before = client.async_get_cleaning.await_count
    await entity.async_press()
    client.async_start_cleaning.assert_awaited_once_with("synthetic-washer", None)
    assert client.async_get_cleaning.await_count == before + 1  # Preflight only.
    assert controls.data.mode_id is None  # No fabricated mode or cycle state.


@pytest.mark.parametrize("kind", ["auth", "rate", "unknown"])
async def test_cleaning_command_failures_are_single_private_requests(controls, kind):
    controls.parent.config_entry = SimpleNamespace(async_start_reauth=Mock())
    entity = entity_for(controls, "button")
    error = {
        "auth": MinijAuthError,
        "rate": MinijRateLimitError,
        "unknown": MinijError,
    }[kind]("private-canary")
    controls.parent.client.async_start_cleaning.side_effect = error
    with pytest.raises(HomeAssistantError) as caught:
        await entity.async_press()
    assert "private-canary" not in str(caught.value)
    assert (
        caught.value.translation_key
        == {
            "auth": "control_auth_failed",
            "rate": "control_rate_limited",
            "unknown": "control_send_uncertain",
        }[kind]
    )
    controls.parent.client.async_start_cleaning.assert_awaited_once()
    assert controls.parent.config_entry.async_start_reauth.call_count == (
        kind == "auth"
    )


async def test_cleaning_metadata_outage_does_not_change_parent_and_blocks_write(
    controls,
):
    entity = entity_for(controls, "button")
    controls.parent.client.async_get_cleaning.side_effect = MinijRateLimitError(
        "private", 1800
    )
    with pytest.raises(HomeAssistantError) as err:
        await entity.async_press()
    assert err.value.translation_key == "control_read_failed"
    assert controls.parent.last_update_success
    assert not entity.available
    controls.parent.client.async_start_cleaning.assert_not_awaited()


async def test_cleaning_unconfirmed_ack_has_bounded_reads_without_resending(controls):
    entity = entity_for(controls)
    client = controls.parent.client
    before = client.async_get_cleaning.await_count
    with patch(
        "custom_components.minij.cleaning.sleep", new_callable=AsyncMock
    ) as wait:
        with pytest.raises(HomeAssistantError) as err:
            await entity.async_turn_off()
    assert err.value.translation_key == "control_not_confirmed"
    assert wait.await_count == 2
    assert client.async_get_cleaning.await_count == before + 4
    client.async_set_cleaning_switch.assert_awaited_once()
    assert entity.is_on is True


async def test_cleaning_controls_serialize_across_platforms(controls):
    import asyncio

    reminder = entity_for(controls)
    button = entity_for(controls, "button")
    client = controls.parent.client
    started, release = asyncio.Event(), asyncio.Event()

    async def delayed_change(device_id, code, enabled):
        started.set()
        await release.wait()
        client.async_get_cleaning.return_value["intelligentBucketCleanRemind"] = enabled

    client.async_set_cleaning_switch.side_effect = delayed_change
    first = asyncio.create_task(reminder.async_turn_off())
    await started.wait()
    second = asyncio.create_task(button.async_press())
    await asyncio.sleep(0)
    client.async_start_cleaning.assert_not_awaited()
    release.set()
    await asyncio.gather(first, second)
    client.async_set_cleaning_switch.assert_awaited_once()
    client.async_start_cleaning.assert_awaited_once_with("synthetic-washer", None)


async def test_cleaning_unload_during_preflight_never_sends(controls):
    entity = entity_for(controls, "button")

    async def read_after_unload(device_id):
        entity._active = False
        return deepcopy(METADATA)

    controls.parent.client.async_get_cleaning.side_effect = read_after_unload
    with pytest.raises(HomeAssistantError) as caught:
        await entity.async_press()
    assert caught.value.translation_key == "control_read_failed"
    controls.parent.client.async_start_cleaning.assert_not_awaited()


async def test_cleaning_unloaded_during_confirmation_does_not_confirm(controls):
    entity = entity_for(controls, "threshold")
    client = controls.parent.client

    async def command(device_id, value):
        async def unloaded(device_id):
            entity._active = False
            data = deepcopy(client.async_get_cleaning.return_value)
            data["bucketCleanRemindBeforeTimes"] = value
            return data

        client.async_get_cleaning.side_effect = unloaded

    client.async_set_cleaning_threshold.side_effect = command
    with pytest.raises(HomeAssistantError) as err:
        await entity.async_select_option("20次")
    assert err.value.translation_key == "control_not_confirmed"
    client.async_set_cleaning_threshold.assert_awaited_once()
