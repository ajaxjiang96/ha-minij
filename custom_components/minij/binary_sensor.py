"""Binary sensors for explicit MiniJ open/close status fields."""

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MinijConfigEntry
from .coordinator import MinijCoordinator
from .entity import MinijEntity

BINARY_SENSORS = (
    BinarySensorEntityDescription(
        key="child_lock_status",
        translation_key="child_lock",
        name="Child lock enabled",
        icon="mdi:lock",
    ),
    BinarySensorEntityDescription(
        key="cloud_control_authorization",
        translation_key="cloud_control_authorized",
        name="Cloud control authorized",
        icon="mdi:cloud-check-outline",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MinijConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add binary sensors for the account's appliances."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def async_add_devices() -> None:
        new_ids = coordinator.data.keys() - known
        known.update(new_ids)
        async_add_entities(
            MinijBinarySensor(coordinator, device_id, description)
            for device_id in new_ids
            for description in BINARY_SENSORS
        )

    async_add_devices()
    entry.async_on_unload(coordinator.async_add_listener(async_add_devices))


class MinijBinarySensor(MinijEntity, BinarySensorEntity):
    """Map only explicit open/close values; preserve unknown as unknown."""

    def __init__(
        self,
        coordinator: MinijCoordinator,
        device_id: str,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the reported boolean field."""
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return a boolean only for the known protocol literals."""
        value = self.characteristics.get(self.entity_description.key)
        if value == "open":
            return True
        if value == "close":
            return False
        return None
