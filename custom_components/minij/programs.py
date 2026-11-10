"""Read the device's own program and parameter choices, independently of status."""

import asyncio
import logging
from asyncio import sleep
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any

from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MinijAuthError, MinijError, MinijRateLimitError
from .const import DOMAIN
from .coordinator import MinijCoordinator
from .entity import MinijEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Program:
    id: str
    name: str
    bid: int
    vid: int
    program_num: int


@dataclass(frozen=True)
class Parameter:
    id: str
    code: str
    name: str
    value: int | None
    options: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ProgramState:
    programs: tuple[Program, ...]
    current_id: str | None
    parameters: tuple[Parameter, ...]
    cloud_catalog_current_id: str | None = None
    selection_source: str = "cloud_catalog"
    draft_choices: tuple[tuple[str, str], ...] = ()
    running_id: str | None = None
    running_parameters: tuple[Parameter, ...] = ()

    @property
    def current(self) -> Program | None:
        return next((x for x in self.programs if x.id == self.current_id), None)


def parse_programs(data: Any) -> tuple[tuple[Program, ...], str | None]:
    """Keep only fields needed to select a server-provided program."""
    if not isinstance(data, dict):
        raise MinijError("MiniJ returned invalid programs")
    records = []
    for key in ("frequentlyDeviceModeVOList", "otherDeviceModeVOList"):
        items = data.get(key)
        if not isinstance(items, list):
            raise MinijError("MiniJ returned invalid program lists")
        records.extend(items)
    current = data.get("currentDeviceMode")
    if current is not None:
        if not isinstance(current, dict):
            raise MinijError("MiniJ returned invalid current program")
        records.append(current)
    programs: dict[str, Program] = {}
    for record in records:
        if not isinstance(record, dict):
            raise MinijError("MiniJ returned invalid program")
        identifier = record.get("id")
        name = record.get("chineseName") or record.get("englishName")
        numbers = [record.get(key) for key in ("bid", "vid", "programNum")]
        if (
            not isinstance(identifier, str)
            or not identifier
            or not isinstance(name, str)
            or not name
            or any(type(value) is not int or not 0 <= value <= 255 for value in numbers)
        ):
            raise MinijError("MiniJ returned invalid program identity")
        program = Program(identifier, name, *numbers)
        if identifier in programs and programs[identifier] != program:
            raise MinijError("MiniJ returned ambiguous program identity")
        programs[identifier] = program
    if len({p.name for p in programs.values()}) != len(programs):
        raise MinijError("MiniJ returned ambiguous program names")
    return tuple(programs.values()), current["id"] if current else None


def parse_parameters(data: Any) -> tuple[Parameter, ...]:
    """Use enum values exactly as returned; never guess units or numeric ranges."""
    if not isinstance(data, dict) or not isinstance(
        data.get("userDeviceModeStatsList"), list
    ):
        raise MinijError("MiniJ returned invalid program parameters")
    result = []
    codes = set()
    for item in data["userDeviceModeStatsList"]:
        if not isinstance(item, dict):
            raise MinijError("MiniJ returned invalid parameter")
        # Non-enumerated future controls have no proven select contract.
        if item.get("type") not in ("choose", "alternative"):
            continue
        identifier, code, name = (item.get(key) for key in ("id", "code", "name"))
        if type(identifier) is int and identifier >= 0:
            identifier = str(identifier)
        values = item.get("optionalValueList")
        if (
            any(not isinstance(x, str) or not x for x in (identifier, code, name))
            or code in codes
            or not isinstance(values, list)
        ):
            raise MinijError("MiniJ returned invalid parameter identity")
        options = []
        for value in values:
            if (
                not isinstance(value, dict)
                or not isinstance(value.get("label"), str)
                or not value["label"]
                or type(value.get("value")) is not int
            ):
                raise MinijError("MiniJ returned invalid parameter option")
            options.append((value["label"], value["value"]))
        if len({x[0] for x in options}) != len(options) or len(
            {x[1] for x in options}
        ) != len(options):
            raise MinijError("MiniJ returned ambiguous parameter options")
        current = item.get("value")
        current = current if type(current) is int else None
        result.append(Parameter(identifier, code, name, current, tuple(options)))
        codes.add(code)
    return tuple(result)


def build_start_parameters(
    parameters: tuple[Parameter, ...], choices: dict[str, str]
) -> list[dict[str, str]]:
    """Resolve option labels against this program's metadata, never global enums."""
    if choices.keys() - {parameter.code for parameter in parameters}:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="program_parameters_changed"
        )
    result = []
    for parameter in parameters:
        if not parameter.options and parameter.code not in choices:
            continue
        label = choices.get(parameter.code)
        if label is None:
            label = next(
                (
                    label
                    for label, value in parameter.options
                    if value == parameter.value
                ),
                None,
            )
        if label not in dict(parameter.options):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="program_parameters_changed"
            )
        result.append(
            {
                "userDeviceModeStatsId": parameter.id,
                "code": parameter.code,
                "value": str(dict(parameter.options)[label]),
            }
        )
    return result


class MinijProgramCoordinator(DataUpdateCoordinator[ProgramState]):
    """One device's metadata and a shared lock for program/parameter commands."""

    def __init__(self, parent: MinijCoordinator, device_id: str) -> None:
        super().__init__(
            parent.hass,
            _LOGGER,
            config_entry=parent.config_entry,
            name="minij programs",
            update_interval=timedelta(seconds=60),
            always_update=False,
        )
        self.parent = parent
        self.device_id = device_id
        self.command_lock = asyncio.Lock()
        self._retry_delay = 60
        self._selection_revision = 0

    def _bound(self) -> bool:
        return self.parent.last_update_success and self.device_id in self.parent.data

    async def _async_update_data(self) -> ProgramState:
        if not self._bound():
            raise UpdateFailed("MiniJ device status unavailable", retry_after=60)
        revision = self._selection_revision
        try:
            programs, cloud_current_id = parse_programs(
                await self.parent.client.async_get_programs(self.device_id)
            )
            local = self.data and self.data.selection_source == "local_draft"
            current_id = (
                self.data.current_id
                if local and any(p.id == self.data.current_id for p in programs)
                else cloud_current_id
            )
            source = (
                "local_draft"
                if local and current_id == self.data.current_id
                else "cloud_catalog"
            )
            parameters = (
                parse_parameters(
                    await self.parent.client.async_get_program_parameters(
                        self.device_id, current_id
                    )
                )
                if current_id is not None
                else ()
            )
            choices = (
                self.data.draft_choices
                if local and current_id == self.data.current_id
                else ()
            )
            running_id, running_parameters = None, ()
            status = (
                self.parent.data.get(self.device_id, {}).get("deviceCharacterMap") or {}
            ).get("current_status_alias")
            if status in ("working", "paused"):
                running_id = await self.parent.client.async_get_running_program(
                    self.device_id
                )
                if running_id:
                    running_parameters = (
                        parameters
                        if running_id == current_id
                        else parse_parameters(
                            await self.parent.client.async_get_program_parameters(
                                self.device_id, running_id
                            )
                        )
                    )
        except MinijAuthError as err:
            raise ConfigEntryAuthFailed("MiniJ rejected the session token") from err
        except MinijError as err:
            if revision != self._selection_revision and self.data is not None:
                return self.data
            delay = self._retry_delay
            self._retry_delay = min(delay * 2, 900)
            if isinstance(err, MinijRateLimitError):
                delay = max(delay, 300, err.retry_after or 0)
            raise UpdateFailed(
                "Unable to read MiniJ program choices", retry_after=delay
            ) from err
        if not self._bound():
            raise UpdateFailed(
                "MiniJ device changed during program read", retry_after=60
            )
        self._retry_delay = 60
        if revision != self._selection_revision and self.data is not None:
            return self.data
        return ProgramState(
            programs,
            current_id,
            parameters,
            cloud_current_id,
            source,
            choices,
            running_id,
            running_parameters,
        )

    @property
    def draft_revision(self) -> int:
        return self._selection_revision

    def pending_label(self, code: str) -> str | None:
        if not self.data:
            return None
        parameter = next((p for p in self.data.parameters if p.code == code), None)
        if parameter is None:
            return None
        selected = dict(self.data.draft_choices).get(code)
        if selected is not None:
            return selected if selected in dict(parameter.options) else None
        return next(
            (label for label, value in parameter.options if value == parameter.value),
            None,
        )

    def pending_signature(self) -> tuple:
        """Capture user-visible choices, independent of refreshed private IDs."""
        if not self.data:
            return ()
        return (
            self.data.current_id,
            self.data.draft_choices,
            tuple((p.code, self.pending_label(p.code)) for p in self.data.parameters),
        )

    def start_parameters(self) -> list[dict[str, str]]:
        """Build only from fresh selected-program metadata, preserving zero."""
        if self.data is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="program_parameters_changed"
            )
        return build_start_parameters(
            self.data.parameters, dict(self.data.draft_choices)
        )

    def select_parameter(self, code: str, label: str) -> None:
        if not self.data:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="program_option_unavailable"
            )
        parameter = next((p for p in self.data.parameters if p.code == code), None)
        if parameter is None or label not in dict(parameter.options):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="program_option_unavailable"
            )
        choices = dict(self.data.draft_choices)
        if choices.get(code) == label:
            return
        choices[code] = label
        self._selection_revision += 1
        self.async_set_updated_data(
            replace(
                self.data,
                draft_choices=tuple(sorted(choices.items())),
                selection_source="local_draft",
            )
        )

    async def async_select_draft(self, program_id: str) -> None:
        """Load a local pending selection; this does not send an appliance command."""
        parameters = parse_parameters(
            await self.parent.client.async_get_program_parameters(
                self.device_id, program_id
            )
        )
        if (
            not self._bound()
            or not self.data
            or not any(p.id == program_id for p in self.data.programs)
        ):
            raise MinijError("MiniJ program changed during selection")
        self._selection_revision += 1
        self.async_set_updated_data(
            replace(
                self.data,
                current_id=program_id,
                parameters=parameters,
                selection_source="local_draft",
                draft_choices=(),
            )
        )

    def diagnostics_snapshot(self) -> dict[str, Any]:
        """Export cache only, excluding account/device/program/parameter IDs."""
        data = self.data
        return {
            "last_refresh_success": self.last_update_success,
            "program_count": len(data.programs) if data else 0,
            "programs": [
                {"name": x.name, "program_num": x.program_num} for x in data.programs
            ]
            if data
            else [],
            "current_program": data.current.name if data and data.current else None,
            "selection_source": data.selection_source if data else None,
            "draft_revision": self.draft_revision,
            "pending_parameters": [
                {"code": p.code, "option": self.pending_label(p.code)}
                for p in data.parameters
            ]
            if data
            else [],
            "running_parameters": [
                {"code": p.code, "value": p.value} for p in data.running_parameters
            ]
            if data
            else [],
            "cloud_catalog_current": next(
                (
                    p.name
                    for p in data.programs
                    if p.id == data.cloud_catalog_current_id
                ),
                None,
            )
            if data
            else None,
            "parameters": [
                {
                    "name": x.name,
                    "code": x.code,
                    "value": x.value,
                    "options": [
                        {"label": label, "value": value} for label, value in x.options
                    ],
                }
                for x in data.parameters
            ]
            if data
            else [],
        }


def program_coordinator(
    parent: MinijCoordinator, device_id: str
) -> MinijProgramCoordinator:
    """Return the one metadata cache used by program selects and start buttons."""
    if not hasattr(parent, "program_controls"):
        parent.program_controls = {}
    if device_id not in parent.program_controls:
        controls = MinijProgramCoordinator(parent, device_id)
        parent.program_controls[device_id] = controls
        parent.hass.async_create_task(controls.async_refresh())
    return parent.program_controls[device_id]


class MinijProgramControl(MinijEntity):
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
            if not self._active or not self.available:
                break
            if predicate():
                return
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="control_not_confirmed"
        )
