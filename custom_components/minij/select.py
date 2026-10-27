"""Device-supplied program and parameter selects without local operating gates."""

from asyncio import sleep
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MinijConfigEntry
from .api import MinijAuthError, MinijError, MinijRateLimitError
from .cleaning import MinijCleaningControl, cleaning_coordinator
from .const import DOMAIN
from .coordinator import MinijCoordinator
from .entity import MinijEntity
from .programs import MinijProgramCoordinator, Parameter

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MinijConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    parent = entry.runtime_data
    parent.program_controls = {}

    @callback
    def discover() -> None:
        for device_id in parent.data.keys() - parent.program_controls.keys():
            controls = MinijProgramCoordinator(parent, device_id)
            parent.program_controls[device_id] = controls
            known: set[str] = set()

            @callback
            def discover_parameters(controls=controls, known=known) -> None:
                if not controls.last_update_success or controls.data is None:
                    return
                parameters = [
                    x for x in controls.data.parameters if x.code not in known
                ]
                known.update(x.code for x in parameters)
                async_add_entities(
                    MinijParameterSelect(parent, controls.device_id, controls, x.code)
                    for x in parameters
                )

            entry.async_on_unload(controls.async_add_listener(discover_parameters))
            async_add_entities([MinijProgramSelect(parent, device_id, controls)])
            hass.async_create_task(controls.async_refresh())

    cleaning_known: set[str] = set()

    @callback
    def discover_cleaning() -> None:
        for device_id in parent.data.keys() - cleaning_known:
            controls = cleaning_coordinator(parent, device_id)
            cleaning_known.add(device_id)
            added: set[str] = set()

            @callback
            def discover_threshold(controls=controls, added=added) -> None:
                if (
                    controls.last_update_success
                    and controls.data is not None
                    and controls.data.options
                    and not added
                ):
                    added.add("threshold")
                    async_add_entities(
                        [
                            MinijCleaningThresholdSelect(
                                parent, controls.device_id, controls
                            )
                        ]
                    )

            entry.async_on_unload(controls.async_add_listener(discover_threshold))
            discover_threshold()

    discover()
    discover_cleaning()
    entry.async_on_unload(parent.async_add_listener(discover))
    entry.async_on_unload(parent.async_add_listener(discover_cleaning))


class MinijProgramControl(MinijEntity, SelectEntity):
    """Share device lifecycle and serialize every program/parameter command."""

    def __init__(
        self,
        parent: MinijCoordinator,
        device_id: str,
        controls: MinijProgramCoordinator,
        key: str,
    ) -> None:
        super().__init__(parent, device_id, key)
        self.controls = controls
        self._active = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._active = True
        self.async_on_remove(
            self.controls.async_add_listener(self.async_write_ha_state)
        )

    async def async_will_remove_from_hass(self) -> None:
        self._active = False
        await super().async_will_remove_from_hass()

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.controls.last_update_success
            and self.controls.data is not None
        )

    async def _fresh(self) -> None:
        if not self._active:
            self._read_failed()
        await self.coordinator.async_refresh()
        if self._active and super().available:
            await self.controls.async_refresh()
        if not self._active or not self.available:
            self._read_failed()

    def _read_failed(self) -> None:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="control_read_failed"
        )

    async def _send(self, operation, *args: Any) -> None:
        try:
            await operation(*args)
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

    async def _confirm(self, predicate) -> None:
        for attempt in range(3):
            if attempt:
                await sleep(2)
            if not self._active:
                break
            await self.controls.async_refresh()
            if not self.available:
                break
            if predicate():
                return
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="control_not_confirmed"
        )


class MinijProgramSelect(MinijProgramControl):
    _attr_name = "Program"
    _attr_translation_key = "program"
    _attr_icon = "mdi:washing-machine"

    def __init__(
        self,
        parent: MinijCoordinator,
        device_id: str,
        controls: MinijProgramCoordinator,
    ) -> None:
        super().__init__(parent, device_id, controls, "program")

    @property
    def options(self) -> list[str]:
        return [x.name for x in self.controls.data.programs] if self.available else []

    @property
    def current_option(self) -> str | None:
        current = self.controls.data.current if self.available else None
        return current.name if current else None

    async def async_select_option(self, option: str) -> None:
        async with self.controls.command_lock:
            await self._fresh()
            target = next(
                (x for x in self.controls.data.programs if x.name == option), None
            )
            if target is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="program_option_unavailable",
                )
            if self.controls.data.current_id == target.id:
                return
            await self._send(
                self.coordinator.client.async_select_program,
                self.device_id,
                target.payload(),
            )
            await self._confirm(lambda: self.controls.data.current_id == target.id)


class MinijParameterSelect(MinijProgramControl):
    _attr_icon = "mdi:tune"

    def __init__(
        self,
        parent: MinijCoordinator,
        device_id: str,
        controls: MinijProgramCoordinator,
        code: str,
    ) -> None:
        super().__init__(parent, device_id, controls, f"parameter_{code}")
        self.code = code
        self._attr_name = self.parameter.name

    @property
    def parameter(self) -> Parameter | None:
        return (
            next(
                (x for x in self.controls.data.parameters if x.code == self.code), None
            )
            if self.controls.data
            else None
        )

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.parameter is not None
            and bool(self.parameter.options)
        )

    @property
    def options(self) -> list[str]:
        return [label for label, _ in self.parameter.options] if self.available else []

    @property
    def current_option(self) -> str | None:
        return (
            next(
                (
                    label
                    for label, value in self.parameter.options
                    if value == self.parameter.value
                ),
                None,
            )
            if self.available
            else None
        )

    async def async_select_option(self, option: str) -> None:
        async with self.controls.command_lock:
            origin = self.controls.data.current_id if self.controls.data else None
            await self._fresh()
            if self.controls.data.current_id != origin:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="program_changed"
                )
            parameter = self.parameter
            target = next(
                (value for label, value in parameter.options if label == option), None
            )
            if target is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="program_option_unavailable",
                )
            if parameter.value == target:
                return
            await self._send(
                self.coordinator.client.async_set_running_parameter,
                self.device_id,
                parameter.id,
                parameter.code,
                target,
            )
            await self._confirm(
                lambda: (
                    self.controls.data.current_id == origin
                    and self.parameter is not None
                    and self.parameter.value == target
                )
            )


class MinijCleaningThresholdSelect(MinijCleaningControl, SelectEntity):
    """Map server-provided display labels back to exact running-count values."""

    _attr_name = "Drum cleaning reminder interval"
    _attr_translation_key = "cleaning_threshold"
    _attr_icon = "mdi:counter"

    def __init__(self, parent, device_id, controls) -> None:
        super().__init__(parent, device_id, controls, "cleaning_threshold")

    @property
    def options(self) -> list[str]:
        return (
            [label for label, _ in self.controls.data.options] if self.available else []
        )

    @property
    def current_option(self) -> str | None:
        return (
            next(
                (
                    label
                    for label, value in self.controls.data.options
                    if value == self.controls.data.threshold
                ),
                None,
            )
            if self.available
            else None
        )

    async def async_select_option(self, option: str) -> None:
        async with self.controls.command_lock:
            await self._fresh()
            target = next(
                (
                    value
                    for label, value in self.controls.data.options
                    if label == option
                ),
                None,
            )
            if target is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="program_option_unavailable",
                )
            if target == self.controls.data.threshold:
                return
            await self._send(
                self.coordinator.client.async_set_cleaning_threshold,
                self.device_id,
                target,
            )
            await self._confirm(lambda: self.controls.data.threshold == target)
