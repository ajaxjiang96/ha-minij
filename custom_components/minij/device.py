"""Map cloud-reported device metadata to Home Assistant device information."""

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def device_info(device_id: str, device: dict[str, Any]) -> DeviceInfo:
    """Keep registration and refresh metadata consistent without changing identity."""
    firmware = " ".join(
        str(device[key])
        for key in ("wifiVersion", "firmwareVersion")
        if device.get(key)
    )
    return DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        manufacturer="MiniJ",
        model=device.get("deviceModel"),
        name=device.get("deviceNickName") or device.get("deviceName") or "MiniJ",
        sw_version=firmware or None,
    )
