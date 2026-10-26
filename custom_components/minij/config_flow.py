"""Configure MiniJ using SMS login or an existing app session token."""

from collections.abc import Mapping
from typing import Any

import probatio
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    MinijAuthError,
    MinijClient,
    MinijError,
    MinijLoginError,
    MinijRateLimitError,
)
from .const import CONF_TOKEN, DOMAIN

TOKEN_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)
PHONE_SCHEMA = probatio.Schema({probatio.Required("phone"): str})
CODE_SCHEMA = probatio.Schema(
    {
        probatio.Required("code"): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)


class MinijConfigFlow(ConfigFlow, domain=DOMAIN):
    """Keep account identity stable and send SMS only on explicit submission."""

    VERSION = 1

    def __init__(self) -> None:
        """Retain pending credentials only for the lifetime of this flow."""
        self._phone = ""
        self._pending_token = ""

    def _client(self, token: str = "") -> MinijClient:
        return MinijClient(async_get_clientsession(self.hass), token)

    async def _async_validate_token(
        self, token: str
    ) -> tuple[str | None, dict[str, str]]:
        """Confirm the account identity and access to the device-list endpoint."""
        if not token:
            return None, {"base": "invalid_auth"}
        client = self._client(token)
        try:
            profile = await client.async_get_profile()
            devices = await client.async_get_devices()
        except MinijAuthError:
            return None, {"base": "invalid_auth"}
        except MinijError:
            return None, {"base": "cannot_connect"}
        user_id = profile.get("userId")
        if not isinstance(user_id, str) or not user_id:
            return None, {"base": "invalid_response"}
        if not devices:
            return None, {"base": "no_devices"}
        return user_id, {}

    async def _async_finish(self, user_id: str, token: str) -> ConfigFlowResult:
        """Create an account or update credentials without replacing its identity."""
        if self.source in (SOURCE_REAUTH, SOURCE_RECONFIGURE):
            entry = (
                self._get_reauth_entry()
                if self.source == SOURCE_REAUTH
                else self._get_reconfigure_entry()
            )
            if user_id != entry.unique_id:
                return self.async_abort(reason="wrong_account")
            return self.async_update_reload_and_abort(
                entry, data_updates={CONF_TOKEN: token}
            )
        await self.async_set_unique_id(user_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="MiniJ", data={CONF_TOKEN: token})

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose an authentication method without making a network request."""
        return self.async_show_menu(step_id="user", menu_options=["phone", "token"])

    async def async_step_phone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Send one login SMS when the user submits their phone number."""
        errors: dict[str, str] = {}
        if user_input is not None:
            phone = user_input["phone"].strip()
            # Only the mainland-China phone format has captured login evidence.
            if len(phone) != 11 or not phone.isascii() or not phone.isdigit():
                errors["phone"] = "invalid_phone"
            elif not phone.startswith("1"):
                errors["phone"] = "invalid_phone"
            else:
                try:
                    await self._client().async_request_sms(phone)
                except MinijRateLimitError:
                    errors["base"] = "rate_limited"
                except MinijLoginError, MinijAuthError:
                    errors["base"] = "sms_rejected"
                except MinijError:
                    errors["base"] = "sms_uncertain"
                else:
                    self._phone = phone
                    return await self.async_step_sms()
        return self.async_show_form(
            step_id="phone", data_schema=PHONE_SCHEMA, errors=errors
        )

    async def async_step_sms(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Exchange the user-entered code once; never resend SMS here."""
        if not self._phone:
            return await self.async_step_phone()
        errors: dict[str, str] = {}
        if user_input is not None:
            code = user_input["code"].strip()
            if not code or not code.isascii() or not code.isdigit():
                errors["code"] = "invalid_code"
            else:
                try:
                    self._pending_token = await self._client().async_login(
                        self._phone, code
                    )
                except MinijRateLimitError:
                    errors["base"] = "rate_limited"
                except MinijLoginError, MinijAuthError:
                    errors["base"] = "login_rejected"
                except MinijError:
                    errors["base"] = "login_uncertain"
                else:
                    self._phone = ""
                    return await self.async_step_validate()
        return self.async_show_form(
            step_id="sms", data_schema=CODE_SCHEMA, errors=errors
        )

    async def async_step_validate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Retry authenticated reads without reusing the SMS code or sending SMS."""
        user_id, errors = await self._async_validate_token(self._pending_token)
        if user_id is not None:
            token, self._pending_token = self._pending_token, ""
            return await self._async_finish(user_id, token)
        if errors.get("base") == "invalid_auth":
            self._pending_token = ""
            return self.async_abort(reason="invalid_auth")
        return self.async_show_form(
            step_id="validate", data_schema=probatio.Schema({}), errors=errors
        )

    async def async_step_token(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate an advanced user's existing app session token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            user_id, errors = await self._async_validate_token(token)
            if user_id is not None:
                return await self._async_finish(user_id, token)
        return self.async_show_form(
            step_id="token", data_schema=TOKEN_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Offer the same SMS/token choices after a rejected session."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose how to reconnect the original account."""
        return self.async_show_menu(
            step_id="reauth_confirm", menu_options=["phone", "token"]
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow an explicit sign-in change without removing a working entry."""
        return self.async_show_menu(
            step_id="reconfigure", menu_options=["phone", "token"]
        )
