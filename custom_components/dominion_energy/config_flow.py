"""Config flow for Dominion Energy Virginia integration.

Implements step-by-step 2FA flow based on dompower library.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .api import (
    DominionEnergyAPI,
    DominionEnergyAPIError,
    InvalidCredentialsError,
    TFARequiredError,
    TFAVerificationError,
    TokenExpiredError,
)
from .const import DOMAIN, CONF_MANUAL_TOKEN

_LOGGER = logging.getLogger(__name__)

# Step 1: Choose authentication method
STEP_AUTH_METHOD_SCHEMA = vol.Schema(
    {
        vol.Required("auth_method", default="automatic"): vol.In({
            "automatic": "Automatic (Username & Password with 2FA)",
            "manual_token": "Manual Token"
        })
    }
)

# Step 2a: Username/Password
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)

# Step 3: 2FA Code
STEP_TFA_CODE_SCHEMA = vol.Schema(
    {
        vol.Required("tfa_code"): cv.string,
    }
)

# Step 2b: Manual token
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
        self.username = None
        self.password = None
        self.tfa_targets = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - choose auth method."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_AUTH_METHOD_SCHEMA,
                description_placeholders={
                    "manual_token_instructions": "Manual token for advanced users only"
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
                    "warning": "Login with two-factor authentication support"
                }
            )

        errors = {}
        self.username = user_input[CONF_USERNAME].strip()
        self.password = user_input[CONF_PASSWORD]

        self.api = DominionEnergyAPI(
            username=self.username,
            password=self.password,
            session=async_get_clientsession(self.hass),
        )

        try:
            # Submit credentials
            result = await self.api.async_submit_credentials()

            if result.get("tfa_required"):
                # 2FA required - get options and move to 2FA step
                _LOGGER.info("2FA required for %s", self.username)

                self.tfa_targets = await self.api.async_get_tfa_options()

                if not self.tfa_targets:
                    errors["base"] = "no_tfa_options"
                else:
                    # Send code to first target (usually phone)
                    await self.api.async_send_tfa_code(self.tfa_targets[0])

                    # Move to 2FA code entry
                    return await self.async_step_tfa_code()
            else:
                # No 2FA needed - exchange for tokens
                tokens = await self.api._async_exchange_for_dominion_tokens()

                await self.async_set_unique_id(self.username)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Dominion Energy - {self.username}",
                    data={
                        "auth_method": "automatic",
                        CONF_USERNAME: self.username,
                        CONF_PASSWORD: self.password,
                        "access_token": tokens.access_token,
                        "refresh_token": tokens.refresh_token,
                        "cookies": self.api.export_cookies(),
                    },
                )

        except InvalidCredentialsError as e:
            _LOGGER.error("Invalid credentials: %s", e)
            errors["base"] = "invalid_auth"

        except DominionEnergyAPIError as e:
            _LOGGER.error("Authentication failed: %s", e)
            errors["base"] = "cannot_connect"

        except Exception as e:
            _LOGGER.exception("Unexpected exception: %s", e)
            errors["base"] = "unknown"

        return self.async_show_form(
            step_id="automatic",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors
        )

    async def async_step_tfa_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle 2FA code entry."""
        if user_input is None:
            # Show which target the code was sent to
            target_info = ""
            if self.tfa_targets:
                target = self.tfa_targets[0]
                target_info = f"Code sent to: {target.target}"

            return self.async_show_form(
                step_id="tfa_code",
                data_schema=STEP_TFA_CODE_SCHEMA,
                description_placeholders={
                    "info": target_info or "Enter the 6-digit verification code"
                }
            )

        errors = {}

        try:
            code = user_input["tfa_code"].strip()

            _LOGGER.info("Verifying 2FA code")

            # Verify code and get tokens
            tokens = await self.api.async_verify_tfa_code(code)

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
                    "access_token": tokens.access_token,
                    "refresh_token": tokens.refresh_token,
                    "cookies": self.api.export_cookies(),
                },
            )

        except TFAVerificationError as e:
            _LOGGER.error("2FA verification failed: %s", e)
            errors["base"] = "invalid_2fa_code"

        except Exception as e:
            _LOGGER.exception("Error during 2FA: %s", e)
            errors["base"] = "unknown"

        return self.async_show_form(
            step_id="tfa_code",
            data_schema=STEP_TFA_CODE_SCHEMA,
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
                        "1. Log in to myaccount.dominionenergy.com\n"
                        "2. Open DevTools (F12) → Network tab\n"
                        "3. Look for requests to prodsvc-dominioncip.smartcmobile.com\n"
                        "4. Copy the Authorization Bearer token and account details"
                    )
                }
            )

        errors = {}

        try:
            token = user_input[CONF_MANUAL_TOKEN].strip()
            account = user_input["account_number"].strip()
            customer = user_input["customer_number"].strip()
            meter = user_input["meter_number"].strip()

            _LOGGER.debug("Manual token validation")

            if not token.startswith("eyJ"):
                _LOGGER.error("Token does not start with eyJ")
                errors["base"] = "invalid_token"
            elif len(token) < 100:
                _LOGGER.error("Token too short")
                errors["base"] = "invalid_token"
            elif not account or not customer or not meter:
                _LOGGER.error("Missing account details")
                errors["base"] = "invalid_token"
            else:
                _LOGGER.info("Token validation passed")

        except Exception as e:
            _LOGGER.exception("Unexpected exception: %s", e)
            errors["base"] = "unknown"
        else:
            if not errors:
                await self.async_set_unique_id(user_input["account_number"])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Dominion Energy - {account}",
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
