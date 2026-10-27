"""Device-supplied cleaning settings shared by controls and diagnostics."""

import asyncio
import logging
from asyncio import sleep
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MinijAuthError, MinijError, MinijRateLimitError
from .const import DOMAIN
from .coordinator import MinijCoordinator
from .entity import MinijEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleaningState:
    mode_id: str | int | None
    trusteeship: bool | None
    reminder: bool | None
    threshold: int | None
    options: tuple[tuple[str, int], ...]
    already_clean_times: int | None


def parse_cleaning(data: Any) -> CleaningState:
    """Keep strict state and allowed values; null trusteeship means unsupported."""
    if not isinstance(data, dict):
        raise MinijError("MiniJ returned invalid cleaning settings")
    options = data.get("optionalValueList")
    if not isinstance(options, list):
        raise MinijError("MiniJ returned invalid cleaning choices")
    choices: list[tuple[str, int]] = []
    for item in options:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("label"), str)
            or not item["label"]
            or type(item.get("value")) is not int
            or item["value"] < 0
        ):
            raise MinijError("MiniJ returned invalid cleaning choice")
        choices.append((item["label"], item["value"]))
    if len({label for label, _ in choices}) != len(choices) or len(
        {value for _, value in choices}
    ) != len(choices):
        raise MinijError("MiniJ returned ambiguous cleaning choices")
    mode_id = data.get("deviceModeId")
    if mode_id is not None and type(mode_id) not in (str, int):
        raise MinijError("MiniJ returned invalid cleaning program")
    return CleaningState(
        mode_id=mode_id,
        trusteeship=data.get("intelligentBucketCleanTrusteeship")
        if type(data.get("intelligentBucketCleanTrusteeship")) is bool
        else None,
        reminder=data.get("intelligentBucketCleanRemind")
        if type(data.get("intelligentBucketCleanRemind")) is bool
        else None,
        threshold=data.get("bucketCleanRemindBeforeTimes")
        if type(data.get("bucketCleanRemindBeforeTimes")) is int
        else None,
        options=tuple(choices),
        already_clean_times=data.get("alreadyCleanTimes")
        if type(data.get("alreadyCleanTimes")) is int
        else None,
    )


class MinijCleaningCoordinator(DataUpdateCoordinator[CleaningState]):
    """Independently poll cleaning metadata; controls share one command lock."""

    def __init__(self, parent: MinijCoordinator, device_id: str) -> None:
        super().__init__(
            parent.hass,
            _LOGGER,
            config_entry=parent.config_entry,
            name="minij cleaning settings",
            update_interval=timedelta(seconds=60),
            always_update=False,
        )
        self.parent = parent
        self.device_id = device_id
        self.command_lock = asyncio.Lock()
        self._retry_delay = 60

    async def _async_update_data(self) -> CleaningState:
        if (
            not self.parent.last_update_success
            or self.device_id not in self.parent.data
        ):
            raise UpdateFailed("MiniJ device status unavailable", retry_after=60)
        try:
            result = parse_cleaning(
                await self.parent.client.async_get_cleaning(self.device_id)
            )
        except MinijAuthError as err:
            raise ConfigEntryAuthFailed("MiniJ rejected the session token") from err
        except MinijError as err:
            delay = self._retry_delay
            self._retry_delay = min(delay * 2, 900)
            if isinstance(err, MinijRateLimitError):
                delay = max(delay, 300, err.retry_after or 0)
            raise UpdateFailed(
                "Unable to fetch MiniJ cleaning settings", retry_after=delay
            ) from err
        if (
            not self.parent.last_update_success
            or self.device_id not in self.parent.data
        ):
            raise UpdateFailed(
                "MiniJ device status changed during settings read", retry_after=60
            )
        self._retry_delay = 60
        return result

    def diagnostics_snapshot(self) -> dict[str, Any]:
        """Export only settings/counters; exclude all device and program IDs."""
        state = self.data
        return {
            "last_update_success": self.last_update_success,
            "trusteeship": state.trusteeship if state else None,
            "reminder": state.reminder if state else None,
            "reminder_threshold": state.threshold if state else None,
            "reminder_options": [value for _, value in state.options] if state else [],
            "already_clean_times": state.already_clean_times if state else None,
        }


def cleaning_coordinator(
    parent: MinijCoordinator, device_id: str
) -> MinijCleaningCoordinator:
    """Return the one metadata cache used across switch/select/button platforms."""
    if not hasattr(parent, "cleaning_controls"):
        parent.cleaning_controls = {}
    if device_id not in parent.cleaning_controls:
        controls = MinijCleaningCoordinator(parent, device_id)
        parent.cleaning_controls[device_id] = controls
        parent.hass.async_create_task(controls.async_refresh())
    return parent.cleaning_controls[device_id]


class MinijCleaningControl(MinijEntity):
    """Fresh capability validation without imposing local machine-state gates."""

    def __init__(self, parent, device_id, controls, key) -> None:
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

    async def _send(self, operation, *args) -> None:
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
