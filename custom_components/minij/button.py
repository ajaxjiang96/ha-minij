"""Explicit appliance commands; cloud acceptance does not imply execution."""

import asyncio

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MinijConfigEntry
from .api import MinijAuthError, MinijError, MinijRateLimitError
from .cleaning import MinijCleaningControl, cleaning_coordinator
from .const import DOMAIN
from .coordinator import MinijCoordinator
from .entity import MinijEntity
from .programs import MinijProgramControl, MinijProgramCoordinator, program_coordinator

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
        entities = []
        for device_id in new_ids:
            entities.extend(
                (
                    MinijWakeButton(parent, device_id),
                    MinijStartProgramButton(
                        parent, device_id, program_coordinator(parent, device_id)
                    ),
                    MinijStartCleaningButton(
                        parent, device_id, cleaning_coordinator(parent, device_id)
                    ),
                )
            )
        async_add_entities(entities)

    discover()
    entry.async_on_unload(parent.async_add_listener(discover))


class MinijWakeButton(MinijEntity, ButtonEntity):
    """Wake a still-bound device without imposing appliance-state conditions."""

    _attr_translation_key = "wake"
    _attr_icon = "mdi:power"
    _attr_entity_registry_enabled_default = True

    def __init__(self, parent: MinijCoordinator, device_id: str) -> None:
        super().__init__(parent, device_id, "wake")
        self._command_lock = asyncio.Lock()
        self._active = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._active = True

    async def async_will_remove_from_hass(self) -> None:
        self._active = False
        await super().async_will_remove_from_hass()

    async def async_press(self) -> None:
        async with self._command_lock:
            if not self._active:
                self._read_failed()
            await self.coordinator.async_refresh()
            if not self._active or not self.available:
                self._read_failed()
            try:
                await self.coordinator.client.async_power_on(self.device_id)
            except MinijAuthError as err:
                self.coordinator.config_entry.async_start_reauth(self.hass)
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="control_auth_failed"
                ) from err
            except MinijRateLimitError as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="control_rate_limited"
                ) from err
            except MinijError as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="control_send_uncertain"
                ) from err
            # The button records an explicit request, not a fabricated waiting state.

    def _read_failed(self) -> None:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="control_read_failed"
        )


class MinijStartCleaningButton(MinijCleaningControl, ButtonEntity):
    """Pass through the current mode ID, including null as the App does."""

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


class MinijStartProgramButton(MinijProgramControl, ButtonEntity):
    """Submit the current pending program, without waking or fabricating a cycle."""

    _attr_translation_key = "start_program"
    _attr_icon = "mdi:play"
    _attr_entity_registry_enabled_default = True

    def __init__(
        self,
        parent: MinijCoordinator,
        device_id: str,
        controls: MinijProgramCoordinator,
    ) -> None:
        super().__init__(parent, device_id, controls, "start_program")

    async def async_press(self) -> None:
        origin_id = self.controls.data.current_id if self.controls.data else None
        async with self.controls.command_lock:
            await self._fresh()
            if self.controls.data.current_id != origin_id:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="program_changed"
                )
            if self.controls.data.current is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="program_option_unavailable",
                )
            await self._send(
                self.coordinator.client.async_start_program,
                self.device_id,
                origin_id,
            )
            # ACK means cloud acceptance; normal status polling supplies cycle state.
