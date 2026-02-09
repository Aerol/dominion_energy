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
        vol.Required("customer_number"): cv.string,
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
        self.api = None
        self.reg_token = None
        self.username = None
        self.password = None

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
                    "warning": "Automatic login with 2FA support"
                }
            )

        errors = {}

        try:
            # Store credentials
            self.username = user_input[CONF_USERNAME].strip()
            self.password = user_input[CONF_PASSWORD]
            
            # Validate credentials by attempting to login
            from homeassistant.helpers.aiohttp_client import async_get_clientsession
            
            self.api = DominionEnergyAPI(
                username=self.username,
                password=self.password,
                session=async_get_clientsession(self.hass),
            )
            
            await self.api.async_login()
            
            # Login succeeded without 2FA - create entry
            await self.async_set_unique_id(self.username)
            self._abort_if_unique_id_configured()
            
            return self.async_create_entry(
                title=f"Dominion Energy - {self.username}",
                data={
                    "auth_method": "automatic",
                    CONF_USERNAME: self.username,
                    CONF_PASSWORD: self.password,
                },
            )
            
        except DominionEnergyAPIError as e:
            error_str = str(e)
            
            # Check if this is a 2FA required error
            if error_str.startswith("2FA_REQUIRED:"):
                # Extract reg_token from error message
                self.reg_token = error_str.split(":", 1)[1]
                _LOGGER.info("2FA required, moving to 2FA step")
                
                # Move to 2FA step
                return await self.async_step_2fa_code()
            else:
                # Other authentication error
                _LOGGER.error("Authentication failed: %s", error_str)
                errors["base"] = "cannot_connect"
                
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"

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
            account = user_input["account_number"].strip()
            customer = user_input["customer_number"].strip()
            meter = user_input["meter_number"].strip()
            
            _LOGGER.debug("Manual token validation - Token starts with: %s, Length: %d", 
                         token[:10], len(token))
            _LOGGER.debug("Account: %s, Customer: %s, Meter: %s", account, customer, meter)
            
            if not token.startswith("eyJ"):
                _LOGGER.error("Token does not start with eyJ")
                errors["base"] = "invalid_token"
            elif len(token) < 100:
                _LOGGER.error("Token too short: %d characters", len(token))
                errors["base"] = "invalid_token"
            elif not account or not customer or not meter:
                _LOGGER.error("Missing account, customer, or meter number")
                errors["base"] = "invalid_token"
            else:
                _LOGGER.info("Token validation passed, creating entry")
                # Skip API validation for now - just accept the token
                
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception during validation: %s", err)
            errors["base"] = "unknown"
        else:
            if not errors:
                # Create the config entry
                await self.async_set_unique_id(user_input["account_number"])
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=f"Dominion Energy - {user_input['account_number']}",
                    data={
                        "auth_method": "manual_token",
                        CONF_MANUAL_TOKEN: token,
                        "account_number": account,
                        "customer_number": customer,
                        "meter_number": meter,
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
    
    async def async_step_2fa_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle 2FA code entry."""
        if user_input is None:
            return self.async_show_form(
                step_id="2fa_code",
                data_schema=vol.Schema({
                    vol.Required("2fa_code"): cv.string,
                }),
                description_placeholders={
                    "info": "A verification code has been sent to your registered phone. Enter the 6-digit code below."
                }
            )
        
        errors = {}
        
        try:
            code = user_input["2fa_code"].strip()
            
            _LOGGER.info("Completing 2FA with code")
            
            # Complete 2FA with the code
            success = await self.api.complete_2fa_login(self.reg_token, code)
            
            if not success:
                _LOGGER.error("2FA completion failed")
                errors["base"] = "invalid_2fa_code"
            else:
                # 2FA successful! Create entry
                await self.async_set_unique_id(self.username)
                self._abort_if_unique_id_configured()
                
                _LOGGER.info("2FA successful, creating config entry")
                
                return self.async_create_entry(
                    title=f"Dominion Energy - {self.username}",
                    data={
                        "auth_method": "automatic",
                        CONF_USERNAME: self.username,
                        CONF_PASSWORD: self.password,
                    },
                )
        
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Error during 2FA: %s", err)
            errors["base"] = "unknown"
        
        return self.async_show_form(
            step_id="2fa_code",
            data_schema=vol.Schema({
                vol.Required("2fa_code"): cv.string,
            }),
            errors=errors
        )

