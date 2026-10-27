"""Coordinate a single device-list request for all MiniJ entities."""

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import MinijAuthError, MinijClient, MinijError, MinijRateLimitError
from .const import DOMAIN
from .device import device_info

_LOGGER = logging.getLogger(__name__)


class MinijCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetch the account's devices once per polling interval."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: MinijClient
    ) -> None:
        """Initialize the shared coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=60),
            always_update=False,
        )
        self.client = client
        self.last_successful_refresh: datetime | None = None
        self.setting_reports: dict[str, dict[str, Any]] = {}
        self._retry_delay = 60

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch devices without issuing appliance commands."""
        try:
            devices = await self.client.async_get_devices()
        except MinijAuthError as err:
            raise ConfigEntryAuthFailed("MiniJ rejected the session token") from err
        except MinijError as err:
            delay = self._retry_delay
            self._retry_delay = min(delay * 2, 900)
            if isinstance(err, MinijRateLimitError):
                delay = max(delay, 300, err.retry_after or 0)
            raise UpdateFailed(
                "Unable to fetch MiniJ device status", retry_after=delay
            ) from err
        self._retry_delay = 60
        self.last_successful_refresh = dt_util.utcnow()
        registry = dr.async_get(self.hass)
        for device in devices:
            device_id = device["deviceId"]
            if registered := registry.async_get_device_by_identifier(
                (DOMAIN, device_id), self.config_entry.entry_id
            ):
                info = device_info(device_id, device)
                registry.async_update_device(
                    registered.id,
                    name=info["name"],
                    model=info["model"],
                    sw_version=info["sw_version"],
                )
        return {device["deviceId"]: device for device in devices}
