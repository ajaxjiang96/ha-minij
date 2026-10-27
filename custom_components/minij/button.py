"""Explicit cleaning command; cloud acceptance does not imply execution."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MinijConfigEntry
from .cleaning import MinijCleaningControl, cleaning_coordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MinijConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    parent = entry.runtime_data
    known: set[str] = set()

    @callback
    def discover() -> None:
        new_ids = parent.data.keys() - known
        known.update(new_ids)
        async_add_entities(
            MinijStartCleaningButton(
                parent, device_id, cleaning_coordinator(parent, device_id)
            )
            for device_id in new_ids
        )

    discover()
    entry.async_on_unload(parent.async_add_listener(discover))


class MinijStartCleaningButton(MinijCleaningControl, ButtonEntity):
    """Pass through the current mode ID, including null as the App does."""

    _attr_name = "Start drum cleaning"
    _attr_translation_key = "start_cleaning"
    _attr_icon = "mdi:washing-machine-alert"

    def __init__(self, parent, device_id, controls) -> None:
        super().__init__(parent, device_id, controls, "start_cleaning")

    async def async_press(self) -> None:
        async with self.controls.command_lock:
            await self._fresh()
            await self._send(
                self.coordinator.client.async_start_cleaning,
                self.device_id,
                self.controls.data.mode_id,
            )
            # Button state is a user action timestamp, never a completion event.
