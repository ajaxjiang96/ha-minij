"""Read the device's own program and parameter choices, independently of status."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MinijAuthError, MinijError, MinijRateLimitError
from .coordinator import MinijCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Program:
    id: str
    name: str
    bid: int
    vid: int
    program_num: int

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bid": self.bid,
            "vid": self.vid,
            "programNum": self.program_num,
        }


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

    def _bound(self) -> bool:
        return self.parent.last_update_success and self.device_id in self.parent.data

    async def _async_update_data(self) -> ProgramState:
        if not self._bound():
            raise UpdateFailed("MiniJ device status unavailable", retry_after=60)
        try:
            programs, current_id = parse_programs(
                await self.parent.client.async_get_programs(self.device_id)
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
        except MinijAuthError as err:
            raise ConfigEntryAuthFailed("MiniJ rejected the session token") from err
        except MinijError as err:
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
        return ProgramState(programs, current_id, parameters)

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
