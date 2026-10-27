"""MiniJ cloud reads and a narrowly scoped experimental controls."""

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import Any
from urllib.parse import urlencode

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
    """MiniJ connection or response failure, without private response text."""

    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


class MinijAuthError(MinijError):
    """The MiniJ session needs authentication."""


class MinijLoginError(MinijError):
    """MiniJ rejected a login request or requires an unsupported challenge."""


class MinijRateLimitError(MinijError):
    """MiniJ requests that the user wait before trying again."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        """Keep the server delay without retaining private response content."""
        super().__init__(message, http_status=429)
        self.retry_after = retry_after


def _retry_after(value: str) -> float | None:
    """Parse HTTP Retry-After seconds or dates; ignore invalid values."""
    value = value.strip()
    if value.isascii() and value.isdigit() and len(value) <= 10:
        return float(value)
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is not None:
            return max(0, (date - datetime.now(UTC)).total_seconds())
    except ValueError, TypeError, OverflowError:
        pass
    return None


NOTIFICATION_EVENTS = {
    "洗衣完成": "wash_completed",
    "清洁完成": "cleaning_completed",
    "故障提醒": "fault_reported",
}


@dataclass(frozen=True)
class DeviceNotification:
    """Minimal internal notification identity, without private message content."""

    message_id: str
    pushed_at: datetime
    event_type: str | None


class MinijClient:
    """Use an externally owned aiohttp session; never log credentials."""

    def __init__(self, session: aiohttp.ClientSession, token: str = "") -> None:
        self._session = session
        self._headers = {**CLIENT_HEADERS, "token": token.strip()}
        self.command_history: deque[dict[str, Any]] = deque(maxlen=30)
        self._device_reports: dict[str, dict[str, Any]] = {}

    async def _request(
        self,
        method: str,
        route: str,
        body: dict[str, Any] | None = None,
        *,
        login_request: bool = False,
    ) -> Any:
        """Perform one request without redirects, retries, or private error text."""
        try:
            async with self._session.request(
                method,
                API_BASE + route,
                headers=CLIENT_HEADERS if login_request else self._headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=20),
                allow_redirects=False,
            ) as response:
                if response.status == 429:
                    raise MinijRateLimitError(
                        "MiniJ rate limit reached",
                        _retry_after(response.headers.get("Retry-After", "")),
                    )
                if response.status in (401, 403):
                    if login_request:
                        raise MinijLoginError("MiniJ rejected the login request")
                    raise MinijAuthError(
                        "MiniJ rejected the session", http_status=response.status
                    )
                if response.status != 200:
                    raise MinijError(
                        f"MiniJ returned HTTP {response.status}",
                        http_status=response.status,
                    )
                payload = await response.json()
        except aiohttp.ClientError, TimeoutError, ValueError:
            raise MinijError("Unable to read MiniJ cloud data") from None
        if not isinstance(payload, dict):
            raise MinijError("MiniJ returned an invalid response")
        if payload.get("success") is not True:
            if login_request:
                raise MinijLoginError("MiniJ did not accept the login request")
            raise MinijError("MiniJ returned an unsuccessful response", http_status=200)
        return payload.get("data")

    async def _get(self, route: str) -> Any:
        return await self._request("GET", route)

    async def async_request_sms(self, phone: str) -> None:
        """Request one login code only on an explicit user action."""
        if not phone.strip():
            raise MinijLoginError("A phone number is required")
        result = await self._request(
            "POST",
            "captcha/sendSmsCaptcha",
            {"phone": phone.strip(), "type": "login"},
            login_request=True,
        )
        # No challenge exchange has been observed. Do not treat a structured
        # challenge or an unexpected payload as a successfully delivered code.
        if result is not None and result is not True:
            raise MinijLoginError("MiniJ returned an unsupported SMS response")

    async def async_login(self, phone: str, code: str) -> str:
        """Exchange one user-entered SMS code, returning only its session token."""
        if not phone.strip() or not code.strip():
            raise MinijLoginError("A phone number and SMS code are required")
        profile = await self._request(
            "POST",
            "login/loginByPhone",
            {"phone": phone.strip(), "captcha": code.strip()},
            login_request=True,
        )
        if not isinstance(profile, dict):
            raise MinijLoginError("MiniJ returned an invalid login response")
        token = profile.get("token")
        if not isinstance(token, str) or not token.strip():
            raise MinijLoginError("MiniJ did not return a session token")
        return token.strip()

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
        self._device_reports = {
            device["deviceId"]: {
                key: value
                for key, value in (device.get("deviceCharacterMap") or {}).items()
                if key
                in (
                    "current_status_alias",
                    "current_mode",
                    "current_process",
                    "child_lock_status",
                    "cloud_control_authorization",
                    "program_remain_time",
                )
                and type(value) in (str, int, bool)
            }
            for device in devices
        }
        return devices

    async def async_get_notifications(self, device_id: str) -> list[DeviceNotification]:
        """Read device messages without marking them read or clearing history."""
        data = await self._request(
            "POST",
            "notificationCenter/findByPage",
            {"type": "DEVICE_NOTIFICATION", "deviceId": device_id},
        )
        if not isinstance(data, dict) or not isinstance(data.get("content"), list):
            raise MinijError("MiniJ returned an invalid notification page")
        notifications = []
        seen = set()
        for record in data["content"]:
            if not isinstance(record, dict):
                raise MinijError("MiniJ returned an invalid notification")
            message_id = record.get("id")
            if (
                not isinstance(message_id, str)
                or not message_id
                or message_id in seen
                or record.get("deviceId") != device_id
                or record.get("type") != "DEVICE_NOTIFICATION"
                or not isinstance(record.get("pushTime"), str)
            ):
                raise MinijError("MiniJ returned invalid notification identity")
            try:
                pushed_at = datetime.strptime(record["pushTime"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                raise MinijError("MiniJ returned invalid notification time") from None
            seen.add(message_id)
            title = record.get("title")
            notifications.append(
                DeviceNotification(
                    message_id,
                    pushed_at,
                    NOTIFICATION_EVENTS.get(title) if isinstance(title, str) else None,
                )
            )
        return notifications

    async def async_set_child_lock(self, device_id: str, enabled: bool) -> None:
        """Submit one explicit single-bucket command without retries or redirects."""
        if not isinstance(device_id, str) or not device_id or type(enabled) is not bool:
            raise MinijError("Invalid child-lock command")
        await self._command(
            "device/switchBasicFunction",
            {
                "deviceId": device_id,
                "basicFunction": "childLock",
                "onOff": enabled,
                "bucketCode": "",
            },
        )

    async def async_get_prompt_tone(self, device_id: str) -> bool | None:
        """Read only the explicit promptTone switch in this device's settings."""
        if not isinstance(device_id, str) or not device_id:
            raise MinijError("Invalid device identifier")
        data = await self._get(
            "device/v3/getDeviceMoreSetting?" + urlencode({"deviceId": device_id})
        )
        if not isinstance(data, dict):
            raise MinijError("MiniJ returned invalid device settings")
        items = data.get("fucntionSettingItemList")
        if not isinstance(items, list) or any(not isinstance(x, dict) for x in items):
            raise MinijError("MiniJ returned invalid function settings")
        matches = [item for item in items if item.get("code") == "promptTone"]
        if not matches:
            return None
        if len(matches) != 1 or type(matches[0].get("switchStatus")) is not bool:
            raise MinijError("MiniJ returned invalid prompt-tone state")
        return matches[0]["switchStatus"]

    async def async_set_prompt_tone(self, device_id: str, enabled: bool) -> None:
        """Submit the website's promptTone boolean once; no guessed bucket/value."""
        if not isinstance(device_id, str) or not device_id or type(enabled) is not bool:
            raise MinijError("Invalid prompt-tone command")
        await self._command(
            "device/switchBasicFunction",
            {"deviceId": device_id, "basicFunction": "promptTone", "onOff": enabled},
        )

    async def async_get_programs(self, device_id: str) -> Any:
        """Read this device's selectable programs and currently selected program."""
        return await self._get(
            "device/v2/getDeviceModeList?"
            + urlencode({"deviceId": device_id, "bucketCode": ""})
        )

    async def async_get_program_parameters(
        self, device_id: str, program_id: str
    ) -> Any:
        return await self._get(
            "device/v2/getUserDeviceMode?"
            + urlencode({"deviceId": device_id, "userDeviceModeId": program_id})
        )

    async def async_set_running_parameter(
        self, device_id: str, parameter_id: str, code: str, value: int
    ) -> None:
        if (
            any(
                not isinstance(item, str) or not item
                for item in (device_id, parameter_id, code)
            )
            or type(value) is not int
        ):
            raise MinijError("Invalid parameter command")
        await self._command(
            "device/v2/workingUserStatsSetup",
            {
                "deviceId": device_id,
                "basicFunction": code,
                "value": str(value),
                "userDeviceModeStatsId": parameter_id,
            },
        )

    async def async_get_cleaning(self, device_id: str) -> Any:
        return await self._get(
            "device/getIntelligentBucketClean?"
            + urlencode({"deviceId": device_id, "bucketCode": ""})
        )

    async def async_set_cleaning_switch(
        self, device_id: str, code: str, enabled: bool
    ) -> None:
        if (
            code
            not in (
                "canSelfCleaningReminder",
                "intelligentSelfCleanTrusteeship",
                "intelligentSelfCleanStartRemindSwitch",
            )
            or type(enabled) is not bool
        ):
            raise MinijError("Invalid cleaning switch command")
        await self._command(
            "device/switchBasicFunction",
            {
                "deviceId": device_id,
                "bucketCode": "",
                "basicFunction": code,
                "onOff": enabled,
            },
        )

    async def async_set_cleaning_threshold(self, device_id: str, value: int) -> None:
        if type(value) is not int:
            raise MinijError("Invalid cleaning threshold")
        await self._command(
            "device/remindAfterCleanTimes",
            {"deviceId": device_id, "bucketCode": "", "cleanTimes": value},
        )

    async def async_start_cleaning(
        self, device_id: str, mode_id: str | int | None
    ) -> None:
        await self._command(
            "device/immediateExecBucketClean",
            {"deviceId": device_id, "bucketCode": "", "deviceModeId": mode_id},
        )

    async def async_power_on(self, device_id: str) -> None:
        """Submit the App's wake operation once, without claiming execution."""
        if not isinstance(device_id, str) or not device_id:
            raise MinijError("Invalid device identifier")
        await self._command(
            "device/v2/deviceOperate",
            {"deviceId": device_id, "bucketCode": "", "operateType": "power_on"},
        )

    async def async_get_running_program(self, device_id: str) -> str | None:
        """Read the running program identity; an idle device returns null."""
        if not isinstance(device_id, str) or not device_id.strip():
            raise MinijError("Invalid device identifier")
        data = await self._get(
            "device/v2/getRunningCurrentDeviceMode?"
            + urlencode({"deviceId": device_id, "bucketCode": ""})
        )
        if data is None:
            return None
        if not isinstance(data, dict):
            raise MinijError("MiniJ returned an invalid running program")
        program_id = data.get("id")
        if not isinstance(program_id, str) or not program_id.strip():
            raise MinijError("MiniJ returned an invalid running program identifier")
        return program_id

    async def async_activate_program(self, device_id: str, program_id: str) -> None:
        """Start or resume with the App's observed empty parameter list, once."""
        await self._program_command(device_id, program_id, "activate")

    async def async_pause_program(self, device_id: str, program_id: str) -> None:
        """Pause the identified running program with one observed request."""
        await self._program_command(device_id, program_id, "pause")

    async def async_power_off(self, device_id: str) -> None:
        """Submit the App's stop/power-off payload once, without program data."""
        if not isinstance(device_id, str) or not device_id.strip():
            raise MinijError("Invalid device identifier")
        await self._command(
            "device/v2/deviceOperate",
            {"deviceId": device_id, "bucketCode": "", "operateType": "power_off"},
        )

    async def _program_command(
        self, device_id: str, program_id: str, operation: str
    ) -> None:
        """Share the exact App payload for activation and pause."""
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (device_id, program_id)
        ):
            raise MinijError("Invalid program command")
        await self._command(
            "device/v2/deviceOperate",
            {
                "deviceId": device_id,
                "bucketCode": "",
                "operateType": operation,
                "activateParam": {
                    "userDeviceModeId": program_id,
                    "userDeviceModeStatsSimpleList": [],
                },
            },
        )

    async def _command(self, route: str, body: dict[str, Any]) -> None:
        """Keep a bounded, credential-free command ledger for owner diagnostics."""
        device_id = body["deviceId"]
        record = {
            "requested_at": datetime.now(UTC).isoformat(),
            "route": route,
            "function": body.get(
                "basicFunction",
                body.get(
                    "operateType",
                    {
                        "device/remindAfterCleanTimes": "cleaning_threshold",
                        "device/immediateExecBucketClean": "cleaning_start",
                    }.get(route, "control"),
                ),
            ),
            "target": body.get(
                "onOff",
                body.get("value", body.get("cleanTimes")),
            ),
            "before": dict(self._device_reports.get(device_id, {})),
            "result": "pending",
        }
        self.command_history.append(record)
        started = monotonic()
        try:
            await self._request("POST", route, body)
        except MinijError as err:
            record["result"] = type(err).__name__
            record["http_status"] = err.http_status
            raise
        else:
            record["result"] = "accepted"
            record["http_status"] = 200
        finally:
            record["duration_ms"] = round((monotonic() - started) * 1000)
