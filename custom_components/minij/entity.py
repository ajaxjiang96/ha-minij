"""Shared MiniJ entity identity and device metadata."""

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import MinijCoordinator
from .device import device_info


class MinijEntity(CoordinatorEntity[MinijCoordinator]):
    """Represent a reported field on one MiniJ appliance."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MinijCoordinator, device_id: str, key: str) -> None:
        """Set stable identity independently of token and display name."""
        super().__init__(coordinator, context=device_id)
        self.device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Expose the current report instead of a metadata snapshot from setup."""
        return device_info(self.device_id, self.device)

    @property
    def device(self) -> dict[str, Any]:
        """Return the current device, including after removal from the account."""
        return self.coordinator.data.get(self.device_id, {})

    @property
    def characteristics(self) -> dict[str, Any]:
        """Return only the controller's reported characteristic map."""
        return self.device.get("deviceCharacterMap") or {}

    @property
    def available(self) -> bool:
        """Require a successful cloud refresh and a still-bound device."""
        return super().available and self.device_id in self.coordinator.data
