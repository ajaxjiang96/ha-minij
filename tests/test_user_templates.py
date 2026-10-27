"""Run the blueprint through HA input expansion, triggers and actions."""

# Fixtures imported from the shared real-HA harness.
# ruff: noqa: F811

from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.automation.config import (
    AUTOMATION_BLUEPRINT_SCHEMA,
    PLATFORM_SCHEMA,
)
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.components.event import DATA_COMPONENT
from homeassistant.components.event.trigger import EventReceivedTrigger
from homeassistant.helpers.script import Script
from homeassistant.helpers.trigger import TriggerConfig
from homeassistant.util.yaml import load_yaml
from test_homeassistant import api, configure, entity_ids, hass  # noqa: F401

from custom_components.minij.api import DeviceNotification, MinijError

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "blueprints/automation/minij/device-notification.yaml"


def expand(entity_id, **inputs):
    blueprint = Blueprint(
        load_yaml(str(BLUEPRINT)),
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
        expected_domain="automation",
    )
    assert blueprint.validate() is None
    instance = BlueprintInputs(
        blueprint,
        {
            "alias": "Synthetic MiniJ notification",
            "use_blueprint": {
                "path": "minij/device-notification.yaml",
                "input": {"notification_entity": entity_id, **inputs},
            },
        },
    )
    instance.validate()
    return PLATFORM_SCHEMA(instance.async_substitute())


async def attach(hass, config):
    trigger_config = dict(config["triggers"][0])
    assert trigger_config.pop("platform") == "event.received"
    trigger_config = await EventReceivedTrigger.async_validate_config(
        hass, trigger_config
    )
    trigger = EventReceivedTrigger(
        hass, TriggerConfig(key="event.received", **trigger_config)
    )
    script = Script(
        hass,
        config["actions"],
        "MiniJ blueprint",
        "automation",
        script_mode=config["mode"],
        max_runs=config["max"],
    )

    async def run(variables, context=None):
        rendered = config["variables"].async_render(hass, variables)
        await script.async_run(rendered, context)

    remove = await trigger.async_attach_action(
        run, lambda payload, _: {"trigger": payload}
    )
    return remove


@pytest.mark.parametrize(
    ("event_type", "title"),
    [
        ("wash_completed", "小吉洗衣完成"),
        ("cleaning_completed", "小吉筒清洁完成"),
        ("fault_reported", "小吉故障提醒"),
    ],
)
async def test_blueprint_default_real_event_to_notification(
    hass, api, event_type, title
):
    """Baseline, duplicate and recovered history do not send notifications."""

    def message(identifier, minute):
        return DeviceNotification(
            identifier, datetime(2026, 1, 1) + timedelta(minutes=minute), event_type
        )

    old = message("old", 0)
    with patch(
        "custom_components.minij.api.MinijClient.async_get_notifications",
        new_callable=AsyncMock,
        return_value=[old],
    ) as messages:
        entry = await configure(hass)
        event_id = entity_ids(hass)["device_notification"]
        event = hass.data[DATA_COMPONENT].get_entity(event_id)
        calls = []
        hass.services.async_register(
            "persistent_notification", "create", lambda call: calls.append(call.data)
        )
        remove = await attach(hass, expand(event_id))
        try:
            await event.notifications.async_refresh()
            await hass.async_block_till_done()
            assert not calls
            messages.return_value = [message("fresh", 1), old]
            await event.notifications.async_refresh()
            await hass.async_block_till_done()
            assert len(calls) == 1
            assert calls[0]["title"] == title
            assert calls[0]["notification_id"] == f"{event_id}_{event_type}"
            assert "小吉云端" in calls[0]["message"]
            await event.notifications.async_refresh()
            await hass.async_block_till_done()
            assert len(calls) == 1
            messages.side_effect = MinijError("Synthetic outage")
            await event.notifications.async_refresh()
            messages.side_effect = None
            messages.return_value.insert(0, message("during-outage", 2))
            await event.notifications.async_refresh()
            await hass.async_block_till_done()
            assert len(calls) == 1
            messages.return_value.insert(0, message("after-recovery", 3))
            await event.notifications.async_refresh()
            await hass.async_block_till_done()
            assert len(calls) == 2
            # A washer state change alone is never a completion signal.
            device = deepcopy(entry.runtime_data.data["washer-test-device"])
            for state in ("working", "resting"):
                device["deviceCharacterMap"]["current_status_alias"] = state
                api[1].return_value = [device]
                await entry.runtime_data.async_refresh()
            await hass.async_block_till_done()
            assert len(calls) == 2
        finally:
            remove()


async def test_blueprint_custom_channel_filter_and_entity_isolation(hass):
    """An action selector receives message variables without fixed phone IDs."""
    event_id = "event.synthetic_minij_notification"
    hass.states.async_set(event_id, "unknown", {"friendly_name": "合成洗衣机通知"})
    hass.states.async_set("event.other_washer", "unknown")
    calls = []
    hass.services.async_register(
        "notify", "synthetic_phone", lambda call: calls.append(call.data)
    )
    config = expand(
        event_id,
        event_types=["wash_completed"],
        notification_actions=[
            {
                "action": "notify.synthetic_phone",
                "data": {
                    "title": "{{ minij_title }}",
                    "message": "{{ minij_message }}",
                    "data": {"source": "{{ minij_notification_entity }}"},
                },
            }
        ],
    )
    remove = await attach(hass, config)
    try:
        for entity, event_type, stamp in (
            ("event.other_washer", "wash_completed", "2026-01-01T00:00:01Z"),
            (event_id, "fault_reported", "2026-01-01T00:00:02Z"),
            (event_id, "cleaning_completed", "2026-01-01T00:00:03Z"),
        ):
            hass.states.async_set(entity, stamp, {"event_type": event_type})
            await hass.async_block_till_done()
        assert not calls
        hass.states.async_set(
            event_id,
            "2026-01-01T00:00:04Z",
            {"event_type": "wash_completed", "friendly_name": "合成洗衣机通知"},
        )
        await hass.async_block_till_done()
        assert len(calls) == 1
        assert calls[0]["title"] == "小吉洗衣完成"
        assert "合成洗衣机通知" in calls[0]["message"]
        assert calls[0]["data"]["source"] == event_id
        assert "{{" not in calls[0]["message"]
    finally:
        remove()
