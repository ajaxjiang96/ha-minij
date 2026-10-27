"""Explicit appliance commands; cloud acceptance does not imply execution."""

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
            controls = program_coordinator(parent, device_id)
            entities.extend(
                (
                    MinijWakeButton(parent, device_id, controls),
                    MinijStartProgramButton(parent, device_id, controls),
                    MinijPauseButton(parent, device_id, controls),
                    MinijResumeButton(parent, device_id, controls),
                    MinijPowerOffButton(parent, device_id, controls),
                    MinijStartCleaningButton(
                        parent, device_id, cleaning_coordinator(parent, device_id)
                    ),
                )
            )
        async_add_entities(entities)

    discover()
    entry.async_on_unload(parent.async_add_listener(discover))


class MinijDeviceCommandButton(MinijEntity, ButtonEntity):
    """Share lifecycle checks and the device's program-command lock."""

    _attr_entity_registry_enabled_default = True

    def __init__(
        self,
        parent: MinijCoordinator,
        device_id: str,
        controls: MinijProgramCoordinator,
    ) -> None:
        super().__init__(parent, device_id, self._attr_translation_key)
        self.controls = controls
        self._active = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._active = True

    async def async_will_remove_from_hass(self) -> None:
        self._active = False
        await super().async_will_remove_from_hass()

    async def async_press(self) -> None:
        async with self.controls.command_lock:
            if not self._active:
                self._read_failed()
            await self.coordinator.async_refresh()
            self._validate_device()
            await self._async_command()
            # The button records an explicit request, not a fabricated cycle state.

    def _validate_device(self) -> None:
        if not self._active or not self.available:
            self._read_failed()

    async def _async_command(self) -> None:
        raise NotImplementedError

    async def _call(self, operation, *args, reading: bool = False):
        try:
            return await operation(*args)
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
                translation_domain=DOMAIN,
                translation_key=(
                    "control_read_failed" if reading else "control_send_uncertain"
                ),
            ) from err

    def _read_failed(self) -> None:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="control_read_failed"
        )


class MinijWakeButton(MinijDeviceCommandButton):
    """Wake a still-bound device without imposing appliance-state conditions."""

    _attr_translation_key = "wake"
    _attr_icon = "mdi:power"

    async def _async_command(self) -> None:
        await self._call(self.coordinator.client.async_power_on, self.device_id)


class MinijRunningProgramButton(MinijDeviceCommandButton):
    """Read actual running identity independently of the pending program draft."""

    async def _running_program(self) -> str:
        program_id = await self._call(
            self.coordinator.client.async_get_running_program,
            self.device_id,
            reading=True,
        )
        self._validate_device()
        if not isinstance(program_id, str) or not program_id.strip():
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="control_no_running_program",
            )
        return program_id


class MinijPauseButton(MinijRunningProgramButton):
    """Pause only the program ID returned by the current running-program read."""

    _attr_translation_key = "pause"
    _attr_icon = "mdi:pause"

    async def _async_command(self) -> None:
        program_id = await self._running_program()
        await self._call(
            self.coordinator.client.async_pause_program, self.device_id, program_id
        )


class MinijResumeButton(MinijRunningProgramButton):
    """Continue the actual running program without activating the local draft."""

    _attr_translation_key = "resume"
    _attr_icon = "mdi:play-pause"

    async def _async_command(self) -> None:
        program_id = await self._running_program()
        await self._call(
            self.coordinator.client.async_activate_program, self.device_id, program_id
        )


class MinijPowerOffButton(MinijDeviceCommandButton):
    """Submit the App's identical stop and power-off operation once."""

    _attr_translation_key = "power_off"
    _attr_icon = "mdi:power-off"

    async def _async_command(self) -> None:
        await self._call(self.coordinator.client.async_power_off, self.device_id)


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
                self.coordinator.client.async_activate_program,
                self.device_id,
                origin_id,
            )
            # ACK means cloud acceptance; normal status polling supplies cycle state.
