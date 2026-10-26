"""Experimental child-lock control, disabled until explicitly enabled by the owner."""

import asyncio
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MinijConfigEntry
from .api import MinijAuthError, MinijError, MinijRateLimitError
from .const import DOMAIN
from .coordinator import MinijCoordinator
from .entity import MinijEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MinijConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register disabled controls only for the target model, including new devices."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def async_add_devices() -> None:
        new_ids = {
            device_id
            for device_id, device in coordinator.data.items()
            if device.get("deviceModel") == "minij.washer.x68"
        } - known
        known.update(new_ids)
        async_add_entities(
            MinijChildLockSwitch(coordinator, device_id) for device_id in new_ids
        )

    async_add_devices()
    entry.async_on_unload(coordinator.async_add_listener(async_add_devices))


class MinijChildLockSwitch(MinijEntity, SwitchEntity):
    """Read actual state; never report a successful toggle from a cloud ACK alone."""

    _attr_translation_key = "child_lock_control"
    _attr_name = "Child lock control (experimental)"
    _attr_icon = "mdi:lock-outline"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: MinijCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "child_lock_control")
        self._command_lock = asyncio.Lock()
        self._control_active = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._control_active = True

    async def async_will_remove_from_hass(self) -> None:
        self._control_active = False
        await super().async_will_remove_from_hass()

    @property
    def is_on(self) -> bool | None:
        value = self.characteristics.get("child_lock_status")
        if value == "open":
            return True
        if value == "close":
            return False
        return None

    def _validate_control(self) -> None:
        """Require a fresh, bound, single-bucket device on the observed firmware."""
        if not self._control_active or not self.available:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="control_read_failed"
            )
        if (
            self.device.get("deviceModel") != "minij.washer.x68"
            or self.device.get("wifiVersion") != "1.0253"
            or self.device.get("firmwareVersion") != "0 0003 1 0000"
            or self.device.get("bucketCode") not in (None, "")
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="control_unsupported"
            )
        if self.characteristics.get("cloud_control_authorization") != "open":
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="control_not_authorized"
            )
        if self.characteristics.get("current_status_alias") != "resting":
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="control_not_idle"
            )
        if self.is_on is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="control_unknown_lock"
            )

    async def _async_set(self, enabled: bool) -> None:
        async with self._command_lock:
            if not self._control_active:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="control_read_failed"
                )
            await self.coordinator.async_refresh()
            self._validate_control()
            if self.is_on is enabled:
                return
            try:
                await self.coordinator.client.async_set_child_lock(
                    self.device_id, enabled
                )
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
            if self._control_active:
                await self.coordinator.async_refresh()
            if (
                not self._control_active
                or not self.available
                or self.is_on is not enabled
            ):
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="control_not_confirmed"
                )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)
