"""Sensors for fields observed in MiniJ device responses."""

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MinijConfigEntry
from .coordinator import MinijCoordinator
from .entity import MinijEntity

KNOWN_STATUSES = ("resting", "working", "device_exception")

SENSORS = (
    SensorEntityDescription(
        key="current_status_alias",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        name="Status",
        icon="mdi:washing-machine",
    ),
    SensorEntityDescription(
        key="current_mode",
        translation_key="reported_program",
        name="Reported program",
        icon="mdi:format-list-bulleted",
    ),
    SensorEntityDescription(
        key="current_process",
        translation_key="reported_process",
        name="Reported process",
        icon="mdi:progress-clock",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MinijConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors, including devices bound after initial setup."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def async_add_devices() -> None:
        new_ids = coordinator.data.keys() - known
        known.update(new_ids)
        async_add_entities(
            MinijSensor(coordinator, device_id, description)
            for device_id in new_ids
            for description in SENSORS
        )

    async_add_devices()
    entry.async_on_unload(coordinator.async_add_listener(async_add_devices))


class MinijSensor(MinijEntity, SensorEntity):
    """A reported status string without speculative enum conversion."""

    def __init__(
        self,
        coordinator: MinijCoordinator,
        device_id: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the reported field."""
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | None:
        """Return the server's field as reported."""
        value = self.characteristics.get(self.entity_description.key)
        return value if isinstance(value, str) and value else None

    @property
    def options(self) -> list[str] | None:
        """Translate known aliases while accepting future raw values unchanged."""
        if self.entity_description.key != "current_status_alias":
            return None
        options = list(KNOWN_STATUSES)
        if (value := self.native_value) is not None and value not in options:
            options.append(value)
        return options

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Keep the server's status label alongside its machine-readable alias."""
        if self.entity_description.key == "current_status_alias":
            value = self.characteristics.get("current_status")
            if isinstance(value, str) and value:
                return {"reported_status": value}
            return None
        alias = self.characteristics.get("current_status_alias")
        return {
            "active_cycle_reported": (
                alias == "working" if alias in ("working", "resting") else None
            )
        }
