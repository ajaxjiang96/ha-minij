"""Export a small allowlist of cached appliance data without account identity."""

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import MinijConfigEntry

_METADATA = ("deviceModel", "deviceType", "wifiVersion", "firmwareVersion")
_CHARACTERISTICS = (
    "current_status_alias",
    "current_status",
    "current_mode",
    "current_process",
    "child_lock_status",
    "cloud_control_authorization",
)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MinijConfigEntry
) -> dict[str, Any]:
    """Return cached observations, never config-entry data or complete responses."""
    coordinator = getattr(entry, "runtime_data", None)
    devices = []
    if coordinator is not None:
        for device in (coordinator.data or {}).values():
            summary: dict[str, Any] = {
                key: value
                for key in _METADATA
                if isinstance(value := device.get(key), str)
            }
            characters = device.get("deviceCharacterMap") or {}
            summary["reported"] = {
                key: value
                for key in _CHARACTERISTICS
                if isinstance(value := characters.get(key), str)
            }
            # Retain the raw flag without guessing physical connectivity.
            flag = device.get("newOrOldAppOnlineStatus")
            if type(flag) is int:
                summary["reported_online_status"] = flag
            devices.append(summary)
    return {
        "captured_at": dt_util.utcnow().isoformat(),
        "entry_state": entry.state.value,
        "last_cloud_refresh_success": (
            coordinator.last_update_success if coordinator is not None else None
        ),
        "last_successful_cloud_refresh": (
            coordinator.last_successful_refresh.isoformat()
            if coordinator is not None
            and coordinator.last_successful_refresh is not None
            else None
        ),
        "cached_devices": devices,
    }
