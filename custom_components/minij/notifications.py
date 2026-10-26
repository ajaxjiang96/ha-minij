"""Poll device notification history independently from appliance state."""

import logging
from datetime import datetime, timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DeviceNotification, MinijAuthError, MinijError, MinijRateLimitError
from .coordinator import MinijCoordinator

_LOGGER = logging.getLogger(__name__)


class NotificationTracker:
    """Identify new message IDs without replaying startup or recovery history."""

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._watermark: datetime | None = None
        self._initialized = False

    def reset_baseline(self) -> None:
        """Suppress the first successful page after an observation gap."""
        self._initialized = False

    def consume(self, records: list[DeviceNotification]) -> list[DeviceNotification]:
        """Return only new, recognized messages at or beyond the time watermark."""
        fresh = [
            record
            for record in sorted(records, key=lambda record: record.pushed_at)
            if record.message_id not in self._seen
            and (self._watermark is None or record.pushed_at >= self._watermark)
            and record.event_type is not None
        ]
        self._seen.update(record.message_id for record in records)
        if records:
            newest = max(record.pushed_at for record in records)
            self._watermark = (
                max(self._watermark, newest) if self._watermark else newest
            )
        if not self._initialized:
            self._initialized = True
            return []
        return fresh


class MinijNotificationCoordinator(DataUpdateCoordinator[list[DeviceNotification]]):
    """Read one device's message page; failures do not hide status sensors."""

    def __init__(self, parent: MinijCoordinator, device_id: str) -> None:
        super().__init__(
            parent.hass,
            _LOGGER,
            config_entry=parent.config_entry,
            name="minij notifications",
            update_interval=timedelta(seconds=60),
            always_update=False,
        )
        self.parent = parent
        self.device_id = device_id
        self.tracker = NotificationTracker()
        self._retry_delay = 60

    async def _async_update_data(self) -> list[DeviceNotification]:
        """Read only for a still-bound device with a successful state refresh."""
        if (
            not self.parent.last_update_success
            or self.device_id not in self.parent.data
        ):
            self.tracker.reset_baseline()
            return []
        try:
            records = await self.parent.client.async_get_notifications(self.device_id)
        except MinijAuthError as err:
            self.tracker.reset_baseline()
            raise ConfigEntryAuthFailed("MiniJ rejected the session token") from err
        except MinijError as err:
            self.tracker.reset_baseline()
            delay = self._retry_delay
            self._retry_delay = min(delay * 2, 900)
            if isinstance(err, MinijRateLimitError):
                delay = max(delay, 300, err.retry_after or 0)
            raise UpdateFailed(
                "Unable to fetch MiniJ notifications", retry_after=delay
            ) from err
        self._retry_delay = 60
        return self.tracker.consume(records)
