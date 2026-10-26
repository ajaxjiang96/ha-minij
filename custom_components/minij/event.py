"""Represent explicit vendor device notifications as HA events."""

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MinijConfigEntry
from .api import NOTIFICATION_EVENTS
from .coordinator import MinijCoordinator
from .entity import MinijEntity
from .notifications import MinijNotificationCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MinijConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add one event entity per supported device without blocking state setup."""
    parent = entry.runtime_data
    known: set[str] = set()

    @callback
    def async_add_devices() -> None:
        new_ids = {
            device_id
            for device_id, device in parent.data.items()
            if device.get("deviceModel") == "minij.washer.x68"
        } - known
        known.update(new_ids)
        async_add_entities(
            MinijNotificationEvent(parent, device_id) for device_id in new_ids
        )

    async_add_devices()
    entry.async_on_unload(parent.async_add_listener(async_add_devices))


class MinijNotificationEvent(MinijEntity, EventEntity):
    """Never infer completion from status, time zero, or notification text fragments."""

    _attr_translation_key = "device_notification"
    _attr_name = "Device notification"
    _attr_icon = "mdi:bell-check-outline"
    _attr_event_types = list(NOTIFICATION_EVENTS.values())

    def __init__(self, parent: MinijCoordinator, device_id: str) -> None:
        super().__init__(parent, device_id, "device_notification")
        self.notifications = MinijNotificationCoordinator(parent, device_id)

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.device.get("deviceModel") == "minij.washer.x68"
            and self.notifications.last_update_success
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # First successful read seeds the baseline; no historical event is fired.
        await self.notifications.async_refresh()
        self.async_on_remove(
            self.notifications.async_add_listener(self._handle_notification_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        if not super().available:
            self.notifications.tracker.reset_baseline()
        super()._handle_coordinator_update()

    @callback
    def _handle_notification_update(self) -> None:
        if self.available:
            for record in self.notifications.data or []:
                if record.event_type is not None:
                    self._trigger_event(record.event_type)
                    self.async_write_ha_state()
        self.async_write_ha_state()
