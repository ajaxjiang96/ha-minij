"""Configure MiniJ with an existing app session token."""

from collections.abc import Mapping
from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import MinijAuthError, MinijClient, MinijError
from .const import CONF_TOKEN, DOMAIN

TOKEN_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)


class MinijConfigFlow(ConfigFlow, domain=DOMAIN):
    """Validate an account and maintain its stable identity through reauth."""

    VERSION = 1

    async def _async_validate_token(
        self, token: str
    ) -> tuple[str | None, dict[str, str]]:
        """Confirm the account identity and access to the device-list endpoint."""
        if not token:
            return None, {"base": "invalid_auth"}
        client = MinijClient(async_get_clientsession(self.hass), token)
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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the first account token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            user_id, errors = await self._async_validate_token(token)
            if user_id is not None:
                await self.async_set_unique_id(user_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="MiniJ", data={CONF_TOKEN: token})
        return self.async_show_form(
            step_id="user", data_schema=TOKEN_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Request a replacement token after authentication is rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace a token only when it belongs to the original account."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            user_id, errors = await self._async_validate_token(token)
            if user_id is not None:
                entry = self._get_reauth_entry()
                if user_id != entry.unique_id:
                    errors["base"] = "wrong_account"
                else:
                    return self.async_update_reload_and_abort(
                        entry, data_updates={CONF_TOKEN: token}
                    )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=TOKEN_SCHEMA, errors=errors
        )
