"""Config flow for Dominion Energy Virginia integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .api import DominionEnergyAPI, DominionEnergyAPIError
from .const import DOMAIN, CONF_MANUAL_TOKEN

_LOGGER = logging.getLogger(__name__)

# Step 1: Choose authentication method
STEP_AUTH_METHOD_SCHEMA = vol.Schema(
    {
        vol.Required("auth_method", default="automatic"): vol.In({
            "automatic": "Automatic (Username & Password) - May not work due to bot detection",
            "manual_token": "Manual Token (Recommended)"
        })
    }
)

# Step 2a: Username/Password (if automatic chosen)
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)

# Step 2b: Manual token (if manual chosen)
STEP_MANUAL_TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MANUAL_TOKEN): cv.string,
        vol.Required("account_number"): cv.string,
        vol.Required("meter_number"): cv.string,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dominion Energy Virginia."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self.auth_method = None
        self.data = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - choose auth method."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", 
                data_schema=STEP_AUTH_METHOD_SCHEMA,
                description_placeholders={
                    "manual_token_instructions": "See WORKAROUND_MANUAL_TOKEN.md for instructions on extracting your token"
                }
            )

        self.auth_method = user_input["auth_method"]
        
        if self.auth_method == "automatic":
            return await self.async_step_automatic()
        else:
            return await self.async_step_manual_token()

    async def async_step_automatic(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle automatic authentication with username/password."""
        if user_input is None:
            return self.async_show_form(
                step_id="automatic", 
                data_schema=STEP_USER_DATA_SCHEMA,
                description_placeholders={
                    "warning": "Note: This may fail due to Gigya bot detection (error 400006)"
                }
            )

        errors = {}

        try:
            # Validate credentials by attempting to login
            from homeassistant.helpers.aiohttp_client import async_get_clientsession
            
            api = DominionEnergyAPI(
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                session=async_get_clientsession(self.hass),
            )
            
            await api.async_login()
            
        except DominionEnergyAPIError:
            errors["base"] = "cannot_connect"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            # Create the config entry
            await self.async_set_unique_id(user_input[CONF_USERNAME])
            self._abort_if_unique_id_configured()
            
            return self.async_create_entry(
                title=f"Dominion Energy - {user_input[CONF_USERNAME]}",
                data={
                    "auth_method": "automatic",
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                },
            )

        return self.async_show_form(
            step_id="automatic", 
            data_schema=STEP_USER_DATA_SCHEMA, 
            errors=errors
        )

    async def async_step_manual_token(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual token authentication."""
        if user_input is None:
            return self.async_show_form(
                step_id="manual_token",
                data_schema=STEP_MANUAL_TOKEN_SCHEMA,
                description_placeholders={
                    "instructions": (
                        "1. Log in to myaccount.dominionenergy.com in your browser\n"
                        "2. Open Developer Tools (F12) → Network tab\n"
                        "3. Look for requests to prodsvc-dominioncip.smartcmobile.com\n"
                        "4. Copy the Authorization Bearer token (starts with eyJ...)\n"
                        "5. Find your account number and meter number in the UI"
                    )
                }
            )

        errors = {}

        try:
            # Basic validation - check token format
            token = user_input[CONF_MANUAL_TOKEN].strip()
            if not token.startswith("eyJ"):
                errors["base"] = "invalid_token"
            else:
                # Test the token by making a simple API call
                from homeassistant.helpers.aiohttp_client import async_get_clientsession
                
                api = DominionEnergyAPI(
                    username="",  # Not needed for manual token
                    password="",
                    session=async_get_clientsession(self.hass),
                )
                
                # Set the manual token and account info
                api._bearer_token = token
                api._account_number = user_input["account_number"]
                api._meter_number = user_input["meter_number"]
                
                # Try to fetch usage data to validate the token
                await api.async_get_usage_data()
                
        except DominionEnergyAPIError:
            errors["base"] = "invalid_token"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            # Create the config entry
            await self.async_set_unique_id(user_input["account_number"])
            self._abort_if_unique_id_configured()
            
            return self.async_create_entry(
                title=f"Dominion Energy - {user_input['account_number']}",
                data={
                    "auth_method": "manual_token",
                    CONF_MANUAL_TOKEN: user_input[CONF_MANUAL_TOKEN],
                    "account_number": user_input["account_number"],
                    "meter_number": user_input["meter_number"],
                },
            )

        if errors:
            return self.async_show_form(
                step_id="manual_token",
                data_schema=STEP_MANUAL_TOKEN_SCHEMA,
                errors=errors
            )

        return self.async_show_form(
            step_id="manual_token",
            data_schema=STEP_MANUAL_TOKEN_SCHEMA
        )
