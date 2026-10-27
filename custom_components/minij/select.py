"""Device-supplied program and parameter selects without local operating gates."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MinijConfigEntry
from .cleaning import MinijCleaningControl, cleaning_coordinator
from .const import DOMAIN
from .coordinator import MinijCoordinator
from .programs import (
    MinijProgramControl,
    MinijProgramCoordinator,
    Parameter,
    program_coordinator,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MinijConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    parent = entry.runtime_data
    known_devices: set[str] = set()

    @callback
    def discover() -> None:
        for device_id in parent.data.keys() - known_devices:
            known_devices.add(device_id)
            controls = program_coordinator(parent, device_id)
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
            discover_parameters()

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


class MinijProgramSelect(MinijProgramControl, SelectEntity):
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
            await self._send(self.controls.async_select_draft, target.id)


class MinijParameterSelect(MinijProgramControl, SelectEntity):
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
        origin = self.controls.data.current_id if self.controls.data else None
        async with self.controls.command_lock:
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
