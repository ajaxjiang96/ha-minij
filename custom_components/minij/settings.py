"""Poll the enabled experimental prompt-tone setting independently of status."""

import logging
from datetime import timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MinijAuthError, MinijError, MinijRateLimitError
from .coordinator import MinijCoordinator

_LOGGER = logging.getLogger(__name__)


class MinijPromptToneCoordinator(DataUpdateCoordinator[bool | None]):
    """A settings outage must not hide existing monitoring entities."""

    def __init__(self, parent: MinijCoordinator, device_id: str) -> None:
        super().__init__(
            parent.hass,
            _LOGGER,
            config_entry=parent.config_entry,
            name="minij prompt tone",
            update_interval=timedelta(seconds=60),
            always_update=False,
        )
        self.parent = parent
        self.device_id = device_id
        self._retry_delay = 60

    async def _async_update_data(self) -> bool | None:
        if (
            not self.parent.last_update_success
            or self.device_id not in self.parent.data
        ):
            raise UpdateFailed("MiniJ device status unavailable", retry_after=60)
        try:
            state = await self.parent.client.async_get_prompt_tone(self.device_id)
        except MinijAuthError as err:
            raise ConfigEntryAuthFailed("MiniJ rejected the session token") from err
        except MinijError as err:
            delay = self._retry_delay
            self._retry_delay = min(delay * 2, 900)
            if isinstance(err, MinijRateLimitError):
                delay = max(delay, 300, err.retry_after or 0)
            raise UpdateFailed(
                "Unable to fetch MiniJ prompt tone", retry_after=delay
            ) from err
        if (
            not self.parent.last_update_success
            or self.device_id not in self.parent.data
        ):
            raise UpdateFailed(
                "MiniJ device status changed during settings read", retry_after=60
            )
        self._retry_delay = 60
        return state
