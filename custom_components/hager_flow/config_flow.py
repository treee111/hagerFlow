"""Config flow for the Hager flow integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    HagerFlowApi,
    HagerFlowAuthError,
    HagerFlowConnectionError,
    HagerFlowError,
)
from .const import CONF_REAUTH_TOKEN, CONF_SERIAL, DOMAIN, PORTAL_URL

_LOGGER = logging.getLogger(__name__)

TOKEN_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, multiline=True)
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SERIAL): str,
        vol.Required(CONF_REAUTH_TOKEN): TOKEN_SELECTOR,
    }
)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_REAUTH_TOKEN): TOKEN_SELECTOR})


class HagerFlowConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setting up and re-authenticating a Hager flow installation."""

    VERSION = 1

    async def _async_validate(self, serial: str, token: str) -> str | None:
        """Return an error key, or None when the credentials work."""
        api = HagerFlowApi(async_get_clientsession(self.hass), token, serial)
        try:
            await api.async_get_status()
        except HagerFlowAuthError:
            return "invalid_auth"
        except HagerFlowConnectionError:
            return "cannot_connect"
        except HagerFlowError:
            return "unknown_serial"
        except Exception:  # noqa: BLE001 - surface as a generic error to the user
            _LOGGER.exception("Unexpected error validating Hager flow credentials")
            return "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            serial = user_input[CONF_SERIAL].strip()
            token = user_input[CONF_REAUTH_TOKEN].strip().strip('"')

            await self.async_set_unique_id(serial)
            self._abort_if_unique_id_configured()

            error = await self._async_validate(serial, token)
            if error is None:
                return self.async_create_entry(
                    title=f"Hager flow {serial}",
                    data={CONF_SERIAL: serial, CONF_REAUTH_TOKEN: token},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={"portal_url": PORTAL_URL},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start re-authentication after the refresh token expired."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh refresh token."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            token = user_input[CONF_REAUTH_TOKEN].strip().strip('"')
            error = await self._async_validate(entry.data[CONF_SERIAL], token)
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_REAUTH_TOKEN: token}
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={
                "serial": entry.data[CONF_SERIAL],
                "portal_url": PORTAL_URL,
            },
        )
