"""Read-only MiniJ cloud API, verified against a V6-XNB."""

from typing import Any

import aiohttp

API_BASE = "https://lilith.minij.com/api/"
CLIENT_HEADERS = {
    "platform": "WEBSITE",
    "version": "1.3.0",
    "spm": "",
    "frp": "",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
}


class MinijError(Exception):
    """MiniJ connection or response failure."""


class MinijAuthError(MinijError):
    """The MiniJ session needs authentication."""


class MinijClient:
    """Use an externally owned aiohttp session; never log credentials."""

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self._session = session
        self._headers = {**CLIENT_HEADERS, "token": token.strip()}

    async def _get(self, route: str) -> Any:
        try:
            async with self._session.get(
                API_BASE + route,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=20),
                allow_redirects=False,
            ) as response:
                if response.status in (401, 403):
                    raise MinijAuthError("MiniJ rejected the session")
                if response.status != 200:
                    raise MinijError(f"MiniJ returned HTTP {response.status}")
                payload = await response.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise MinijError("Unable to read MiniJ cloud data") from err
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise MinijError("MiniJ returned an unsuccessful response")
        return payload.get("data")

    async def async_get_profile(self) -> dict[str, str]:
        """Return only stable account identity, excluding profile secrets."""
        profile = await self._get("personal/getUserProfile")
        if not isinstance(profile, dict) or not isinstance(profile.get("userId"), str):
            raise MinijError("MiniJ returned an invalid account profile")
        if not profile["userId"]:
            raise MinijError("MiniJ returned an empty account identifier")
        return {"userId": profile["userId"]}

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Read the account's bound devices and their reported status."""
        devices = await self._get("device/getUserBindDeviceList")
        if not isinstance(devices, list):
            raise MinijError("MiniJ returned an invalid device list")
        seen = set()
        for device in devices:
            if not isinstance(device, dict):
                raise MinijError("MiniJ returned an invalid device record")
            device_id = device.get("deviceId")
            if not isinstance(device_id, str) or not device_id or device_id in seen:
                raise MinijError("MiniJ returned an invalid device identifier")
            seen.add(device_id)
            characters = device.get("deviceCharacterMap")
            if characters is not None and not isinstance(characters, dict):
                raise MinijError("MiniJ returned invalid device status")
        return devices
