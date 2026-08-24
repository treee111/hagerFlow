"""Config flow for the Hager flow integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import HagerFlowApi
from .api_official import HagerFlowOfficialApi
from .backend import (
    HagerFlowAuthError,
    HagerFlowConnectionError,
    HagerFlowError,
)
from .const import (
    BACKEND_OFFICIAL,
    BACKEND_PORTAL,
    CONF_BACKEND,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_INSTALLATION_ID,
    CONF_REAUTH_TOKEN,
    CONF_SERIAL,
    DEVELOPER_PORTAL_URL,
    DOMAIN,
    PORTAL_URL,
)

_LOGGER = logging.getLogger(__name__)

SECRET_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
TOKEN_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, multiline=True)
)

STEP_PORTAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SERIAL): str,
        vol.Required(CONF_REAUTH_TOKEN): TOKEN_SELECTOR,
    }
)

STEP_OFFICIAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): SECRET_SELECTOR,
    }
)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_REAUTH_TOKEN): TOKEN_SELECTOR})


class HagerFlowConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setting up and re-authenticating a Hager flow installation."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise per-flow state."""
        # Carried between the credentials step and the installation picker.
        self._credentials: dict[str, str] = {}
        self._installations: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick which backend to connect to."""
        return self.async_show_menu(
            step_id="user", menu_options=[BACKEND_OFFICIAL, BACKEND_PORTAL]
        )

    # --- the official API -------------------------------------------------

    async def async_step_official(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the OAuth client credentials and list the installations."""
        errors: dict[str, str] = {}

        if user_input is not None:
            client_id = user_input[CONF_CLIENT_ID].strip()
            client_secret = user_input[CONF_CLIENT_SECRET].strip()

            api = HagerFlowOfficialApi(
                async_get_clientsession(self.hass), client_id, client_secret
            )
            try:
                self._installations = await api.async_get_installations()
            except HagerFlowAuthError:
                errors["base"] = "invalid_auth"
            except HagerFlowConnectionError:
                errors["base"] = "cannot_connect"
            except HagerFlowError:
                errors["base"] = "unknown"
            except Exception:  # noqa: BLE001 - surface as a generic error
                _LOGGER.exception("Unexpected error validating API credentials")
                errors["base"] = "unknown"
            else:
                if not self._installations:
                    errors["base"] = "no_installations"
                else:
                    self._credentials = {
                        CONF_CLIENT_ID: client_id,
                        CONF_CLIENT_SECRET: client_secret,
                    }
                    # One installation is the normal case; only ask when the
                    # credentials really cover several.
                    if len(self._installations) == 1:
                        return await self._async_create_official(
                            str(self._installations[0].get("id"))
                        )
                    return await self.async_step_installation()

        return self.async_show_form(
            step_id="official",
            data_schema=STEP_OFFICIAL_SCHEMA,
            errors=errors,
            description_placeholders={"developer_portal_url": DEVELOPER_PORTAL_URL},
        )

    async def async_step_installation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick one of several installations the credentials have access to."""
        if user_input is not None:
            return await self._async_create_official(user_input[CONF_INSTALLATION_ID])

        options = [
            {
                "value": str(item.get("id")),
                "label": f"{item.get('name') or item.get('id')}",
            }
            for item in self._installations
        ]
        return self.async_show_form(
            step_id="installation",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_INSTALLATION_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=options, mode=SelectSelectorMode.LIST
                        )
                    )
                }
            ),
        )

    async def _async_create_official(self, installation_id: str) -> ConfigFlowResult:
        """Store an entry for the official backend."""
        await self.async_set_unique_id(installation_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            # Name the route, not just the number: a serial and an installation
            # id look alike, and both routes can be set up side by side.
            title=f"Hager flow {installation_id} (official API)",
            data={
                CONF_BACKEND: BACKEND_OFFICIAL,
                CONF_INSTALLATION_ID: installation_id,
                **self._credentials,
            },
        )

    # --- the flow portal --------------------------------------------------

    async def _async_validate_portal(self, serial: str, token: str) -> str | None:
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

    async def async_step_portal(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up against the undocumented portal API."""
        errors: dict[str, str] = {}

        if user_input is not None:
            serial = user_input[CONF_SERIAL].strip()
            token = user_input[CONF_REAUTH_TOKEN].strip().strip('"')

            await self.async_set_unique_id(serial)
            self._abort_if_unique_id_configured()

            error = await self._async_validate_portal(serial, token)
            if error is None:
                return self.async_create_entry(
                    title=f"Hager flow {serial} (flow portal)",
                    data={
                        CONF_BACKEND: BACKEND_PORTAL,
                        CONF_SERIAL: serial,
                        CONF_REAUTH_TOKEN: token,
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="portal",
            data_schema=STEP_PORTAL_SCHEMA,
            errors=errors,
            description_placeholders={"portal_url": PORTAL_URL},
        )

    # --- re-authentication ------------------------------------------------

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start re-authentication after the credentials stopped working."""
        if entry_data.get(CONF_BACKEND) == BACKEND_OFFICIAL:
            return await self.async_step_reauth_official()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_official(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for replacement OAuth client credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            client_id = user_input[CONF_CLIENT_ID].strip()
            client_secret = user_input[CONF_CLIENT_SECRET].strip()
            api = HagerFlowOfficialApi(
                async_get_clientsession(self.hass),
                client_id,
                client_secret,
                entry.data[CONF_INSTALLATION_ID],
            )
            try:
                await api.async_get_energy_current()
            except HagerFlowAuthError:
                errors["base"] = "invalid_auth"
            except HagerFlowConnectionError:
                errors["base"] = "cannot_connect"
            except HagerFlowError:
                errors["base"] = "unknown"
            except Exception:  # noqa: BLE001 - surface as a generic error
                _LOGGER.exception("Unexpected error validating API credentials")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_CLIENT_ID: client_id,
                        CONF_CLIENT_SECRET: client_secret,
                    },
                )

        return self.async_show_form(
            step_id="reauth_official",
            data_schema=STEP_OFFICIAL_SCHEMA,
            errors=errors,
            description_placeholders={
                "installation_id": str(entry.data[CONF_INSTALLATION_ID]),
                "developer_portal_url": DEVELOPER_PORTAL_URL,
            },
        )

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh refresh token."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            token = user_input[CONF_REAUTH_TOKEN].strip().strip('"')
            error = await self._async_validate_portal(entry.data[CONF_SERIAL], token)
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
