"""Coordinate a single device-list request for all MiniJ entities."""

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MinijAuthError, MinijClient, MinijError
from .const import DOMAIN

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

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch devices without issuing appliance commands."""
        try:
            devices = await self.client.async_get_devices()
        except MinijAuthError as err:
            raise ConfigEntryAuthFailed("MiniJ rejected the session token") from err
        except MinijError as err:
            raise UpdateFailed("Unable to fetch MiniJ device status") from err
        return {str(device["deviceId"]): device for device in devices}
