"""Sensors for fields observed in MiniJ device responses."""

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import UnitOfTime
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
    SensorEntityDescription(
        key="program_remain_time",
        translation_key="reported_remaining_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        name="Reported remaining time",
        icon="mdi:timer-sand",
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
            if description.key != "program_remain_time"
            or coordinator.data[device_id].get("deviceModel") == "minij.washer.x68"
        )

    async_add_devices()
    entry.async_on_unload(coordinator.async_add_listener(async_add_devices))


class MinijSensor(MinijEntity, SensorEntity):
    """A raw report or model-verified duration without local countdown."""

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
    def native_value(self) -> str | int | None:
        """Return the server's field as reported."""
        value = self.characteristics.get(self.entity_description.key)
        if self.entity_description.key == "program_remain_time":
            if (
                self.device.get("deviceModel") != "minij.washer.x68"
                or self.characteristics.get("current_status_alias") != "working"
            ):
                return None
            if type(value) is int:
                return value if value >= 0 else None
            if isinstance(value, str) and value.isascii() and value.isdigit():
                try:
                    return int(value)
                except ValueError:
                    return None
            return None
        return value if isinstance(value, str) and value else None

    @property
    def options(self) -> list[str] | None:
        """Translate known aliases while accepting future raw values unchanged."""
        if self.entity_description.key != "current_status_alias":
            return None
        options = list(KNOWN_STATUSES)
        if isinstance(value := self.native_value, str) and value not in options:
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
