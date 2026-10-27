"""Device controls with cloud-enforced appliance permissions and conditions."""

import asyncio
from asyncio import sleep
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MinijConfigEntry
from .api import MinijAuthError, MinijError, MinijRateLimitError
from .cleaning import MinijCleaningControl, cleaning_coordinator
from .const import DOMAIN
from .coordinator import MinijCoordinator
from .entity import MinijEntity
from .settings import MinijSettingCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MinijConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register controls for bound devices, including devices added after setup."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def async_add_devices() -> None:
        new_ids = coordinator.data.keys() - known
        known.update(new_ids)
        async_add_entities(
            entity(coordinator, device_id)
            for device_id in new_ids
            for entity in (MinijChildLockSwitch, MinijPromptToneSwitch)
        )

    cleaning_known: dict[str, set[str]] = {}

    @callback
    def discover_cleaning() -> None:
        for device_id in coordinator.data.keys() - cleaning_known.keys():
            controls = cleaning_coordinator(coordinator, device_id)
            known_keys: set[str] = set()
            cleaning_known[device_id] = known_keys

            @callback
            def discover_switches(controls=controls, known_keys=known_keys) -> None:
                if not controls.last_update_success or controls.data is None:
                    return
                for key, value in (
                    ("cleaning_trusteeship", controls.data.trusteeship),
                    ("cleaning_reminder", controls.data.reminder),
                ):
                    if type(value) is bool and key not in known_keys:
                        known_keys.add(key)
                        async_add_entities(
                            [
                                MinijCleaningSwitch(
                                    coordinator, controls.device_id, controls, key
                                )
                            ]
                        )

            entry.async_on_unload(controls.async_add_listener(discover_switches))
            discover_switches()

    async_add_devices()
    discover_cleaning()
    entry.async_on_unload(coordinator.async_add_listener(async_add_devices))
    entry.async_on_unload(coordinator.async_add_listener(discover_cleaning))


class MinijControlSwitch(MinijEntity, SwitchEntity):
    """Read actual state; never report a successful toggle from a cloud ACK alone."""

    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator: MinijCoordinator, device_id: str, key: str) -> None:
        super().__init__(coordinator, device_id, key)
        self._command_lock = asyncio.Lock()
        self._control_active = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._control_active = True

    async def async_will_remove_from_hass(self) -> None:
        self._control_active = False
        await super().async_will_remove_from_hass()

    def _validate_device(self) -> None:
        """Require a live entity and a successful read of a still-bound device."""
        if not self._control_active or not self.available:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="control_read_failed"
            )

    async def _async_refresh_control(self) -> None:
        await self.coordinator.async_refresh()

    async def _async_send(self, enabled: bool) -> None:
        raise NotImplementedError

    async def _async_confirm(self, enabled: bool) -> None:
        if self._control_active:
            await self._async_refresh_control()

    def _validate_control(self) -> None:
        raise NotImplementedError

    async def _async_set(self, enabled: bool) -> None:
        async with self._command_lock:
            if not self._control_active:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="control_read_failed"
                )
            await self._async_refresh_control()
            self._validate_control()
            if self.is_on is enabled:
                return
            try:
                await self._async_send(enabled)
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
            await self._async_confirm(enabled)
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


class MinijChildLockSwitch(MinijControlSwitch):
    """Retain the pending child-lock candidate; real running-state proof is absent."""

    _attr_translation_key = "child_lock_control"
    _attr_name = "Child lock control (experimental)"
    _attr_icon = "mdi:lock-outline"

    def __init__(self, coordinator: MinijCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "child_lock_control")

    @property
    def is_on(self) -> bool | None:
        value = self.characteristics.get("child_lock_status")
        if value == "open":
            return True
        if value == "close":
            return False
        return None

    def _validate_control(self) -> None:
        self._validate_device()
        if self.is_on is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="control_unknown_lock"
            )

    async def _async_send(self, enabled: bool) -> None:
        await self.coordinator.client.async_set_child_lock(self.device_id, enabled)


class MinijPromptToneSwitch(MinijControlSwitch):
    """Only settings switchStatus is authoritative; never infer from a cloud ACK."""

    _key = "prompt_tone"
    _setting_code = "promptTone"
    _attr_translation_key = "prompt_tone"
    _attr_name = "Prompt tone (experimental)"
    _attr_icon = "mdi:volume-high"

    def __init__(self, coordinator: MinijCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, self._key)
        self.settings = MinijSettingCoordinator(
            coordinator, device_id, self._setting_code
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self.settings.async_refresh()
        self.async_on_remove(
            self.settings.async_add_listener(self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        return super().available and self.settings.last_update_success

    @property
    def is_on(self) -> bool | None:
        return self.settings.data

    async def _async_refresh_control(self) -> None:
        await self.coordinator.async_refresh()
        if self._control_active and super().available:
            await self.settings.async_refresh()

    def _validate_control(self) -> None:
        self._validate_device()
        if type(self.is_on) is not bool:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="prompt_tone_not_supported"
            )

    async def _async_send(self, enabled: bool) -> None:
        await self.coordinator.client.async_set_prompt_tone(self.device_id, enabled)

    async def _async_confirm(self, enabled: bool) -> None:
        """Allow delayed settings reports: at most three reads, never another write."""
        for attempt in range(3):
            if attempt:
                await sleep(2)
            if not self._control_active:
                return
            await self._async_refresh_control()
            if not self.available or self.is_on is enabled or self.is_on is None:
                return


class MinijCleaningSwitch(MinijCleaningControl, SwitchEntity):
    """Use the dedicated cleaning page; its more-settings menu is not a switch."""

    _attr_icon = "mdi:washing-machine-alert"

    def __init__(self, parent, device_id, controls, key) -> None:
        super().__init__(parent, device_id, controls, key)
        self.key = key
        self._attr_translation_key = key
        self._attr_name = (
            "Automatic drum cleaning"
            if key == "cleaning_trusteeship"
            else "Drum cleaning reminder"
        )

    @property
    def is_on(self) -> bool | None:
        if not self.controls.data:
            return None
        return (
            self.controls.data.trusteeship
            if self.key == "cleaning_trusteeship"
            else self.controls.data.reminder
        )

    async def _set(self, enabled: bool) -> None:
        async with self.controls.command_lock:
            await self._fresh()
            if type(self.is_on) is not bool:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="cleaning_setting_unavailable",
                )
            if self.is_on is enabled:
                return
            state = self.controls.data
            code = (
                "intelligentSelfCleanTrusteeship"
                if self.key == "cleaning_trusteeship"
                else "intelligentSelfCleanStartRemindSwitch"
                if state.trusteeship is True
                else "canSelfCleaningReminder"
            )
            await self._send(
                self.coordinator.client.async_set_cleaning_switch,
                self.device_id,
                code,
                enabled,
            )
            await self._confirm(lambda: self.is_on is enabled)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
