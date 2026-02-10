"""API Client for Dominion Energy Virginia.

Based on dompower library: https://github.com/YeomansIII/dompower
Implements complete 2FA flow and token refresh.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any
from datetime import datetime, timedelta, UTC
from urllib.parse import urlencode
from pathlib import Path
from enum import Enum

import aiohttp

_LOGGER = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS (from dompower/const.py)
# ============================================================================

# Dominion API
BASE_URL = "https://prodsvc-dominioncip.smartcmobile.com"
ENDPOINT_LOGIN = "/UsermanagementAPI/api/1/Login/auth"
ENDPOINT_REFRESH = "/UsermanagementAPI/api/1/login/auth/refresh"
ENDPOINT_USAGE = "/UsermanagementAPI/api/1/Usage"
ENDPOINT_ACCOUNTS = "/UsermanagementAPI/api/1/Account"

DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "uid": "1",
    "pt": "1",
    "channel": "WEB",
    "Origin": "https://myaccount.dominionenergy.com",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_0) "
        "AppleWebKit/537.00 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.00"
    ),
}

# Gigya Authentication
GIGYA_API_KEY = "4_6zEg-HY_0eqpgdSONYkJkQ"
GIGYA_BASE_URL = "https://auth.dominionenergy.com"
GIGYA_SDK_VERSION = "js_latest"
GIGYA_SDK_BUILD = "18148"
LOGIN_URL = "https://login.dominionenergy.com/CommonLogin?SelectedAppName=Electric"

# Gigya Endpoints
GIGYA_BOOTSTRAP = "/accounts.webSdkBootstrap"
GIGYA_LOGIN = "/accounts.login"
GIGYA_TFA_PROVIDERS = "/accounts.tfa.getProviders"
GIGYA_TFA_INIT = "/accounts.tfa.initTFA"
GIGYA_TFA_FINALIZE = "/accounts.tfa.finalizeTFA"
GIGYA_FINALIZE_REGISTRATION = "/accounts.finalizeRegistration"
GIGYA_TFA_PHONE_NUMBERS = "/accounts.tfa.phone.getRegisteredPhoneNumbers"
GIGYA_TFA_SEND_PHONE = "/accounts.tfa.phone.sendVerificationCode"
GIGYA_TFA_VERIFY_PHONE = "/accounts.tfa.phone.completeVerification"
GIGYA_TFA_EMAILS = "/accounts.tfa.email.getEmails"
GIGYA_TFA_SEND_EMAIL = "/accounts.tfa.email.sendVerificationCode"
GIGYA_TFA_VERIFY_EMAIL = "/accounts.tfa.email.completeVerification"
GIGYA_ACCOUNT_INFO = "/accounts.getAccountInfo"

# Gigya Error Codes
GIGYA_ERROR_TFA_PENDING = 403101
GIGYA_ERROR_INVALID_LOGIN = 403042
GIGYA_ERROR_INVALID_PASSWORD = 403043
GIGYA_ERROR_INVALID_JWT = 400006

# Token expiration
ACCESS_TOKEN_EXPIRY_MINUTES = 30


# ============================================================================
# EXCEPTIONS
# ============================================================================

class DominionEnergyAPIError(Exception):
    """Base exception for Dominion Energy API errors."""


class InvalidCredentialsError(DominionEnergyAPIError):
    """Invalid username or password."""


class TFARequiredError(DominionEnergyAPIError):
    """Two-factor authentication is required."""
    
    def __init__(self, message: str, reg_token: str = None, gigya_assertion: str = None):
        super().__init__(message)
        self.reg_token = reg_token
        self.gigya_assertion = gigya_assertion


class TFAVerificationError(DominionEnergyAPIError):
    """TFA code verification failed."""


class TokenExpiredError(DominionEnergyAPIError):
    """Token has expired."""


# ============================================================================
# MODELS
# ============================================================================

class TFAProvider(Enum):
    """TFA provider types."""
    PHONE = "gigyaPhone"
    EMAIL = "gigyaEmail"


class TFATarget:
    """Represents a 2FA target (phone number or email)."""
    
    def __init__(self, provider: TFAProvider, target: str, id: str = ""):
        self.provider = provider
        self.target = target  # Obfuscated phone/email shown to user
        self.id = id  # Internal ID for API calls


class TokenPair:
    """Access and refresh tokens."""
    
    def __init__(self, access_token: str, refresh_token: str, expires_at: datetime = None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at or (datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRY_MINUTES))


# ============================================================================
# API CLIENT
# ============================================================================

class DominionEnergyAPI:
    """API client for Dominion Energy Virginia with 2FA support."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        access_token: str = None,
        refresh_token: str = None,
    ) -> None:
        """Initialize the API client.
        
        Args:
            username: Dominion Energy email
            password: Account password
            session: aiohttp ClientSession
            access_token: Existing access token (optional)
            refresh_token: Existing refresh token (optional)
        """
        self.username = username
        self.password = password
        self.session = session
        
        # Tokens
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._token_expires_at: datetime | None = None
        if access_token:
            self._token_expires_at = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRY_MINUTES)
        
        # Gigya session state for 2FA
        self._reg_token: str | None = None
        self._gigya_assertion: str | None = None
        self._phv_token: str | None = None
        self._tfa_target: TFATarget | None = None
        self._gigya_id_token: str | None = None
        self._gigya_uid: str | None = None
        
        # Account info
        self._account_number = None
        self._customer_number = None
        self._meter_number = None
        
        # Cookies for 2FA bypass
        self._cookies: dict[str, Any] = {}

    # ========================================================================
    # TOKEN MANAGEMENT
    # ========================================================================

    @property
    def has_tokens(self) -> bool:
        """Check if we have both access and refresh tokens."""
        return self._access_token is not None and self._refresh_token is not None

    @property
    def is_token_expired(self) -> bool:
        """Check if the access token has expired."""
        if self._token_expires_at is None:
            return True
        # Add 30 second buffer
        return datetime.now(UTC) >= (self._token_expires_at - timedelta(seconds=30))

    async def async_refresh_token(self) -> bool:
        """Refresh the access token using the refresh token.
        
        Based on dompower/auth.py:async_refresh_tokens()
        
        Returns:
            True if refresh successful, False otherwise
        """
        if not self._refresh_token:
            _LOGGER.error("No refresh token available")
            return False

        if not self._access_token:
            _LOGGER.error("No access token available for refresh")
            return False

        url = f"{BASE_URL}{ENDPOINT_REFRESH}"
        headers = {
            **DEFAULT_HEADERS,
            "Authorization": f"Bearer {self._access_token}",
        }
        payload = {"refreshToken": self._refresh_token}

        _LOGGER.debug("Refreshing access token")

        try:
            async with self.session.post(url, headers=headers, json=payload) as response:
                if response.status == 401:
                    _LOGGER.error("Refresh token expired - re-authentication required")
                    raise TokenExpiredError("Refresh token expired")

                if response.status != 200:
                    text = await response.text()
                    _LOGGER.error("Token refresh failed: %s - %s", response.status, text)
                    return False

                data = await response.json()

        except TokenExpiredError:
            raise
        except Exception as err:
            _LOGGER.exception("Failed to refresh token: %s", err)
            return False

        # Extract new tokens from response
        # Response: {"status": {...}, "data": {"accessToken": ..., "refreshToken": ...}}
        status = data.get("status", {})
        if status.get("code") != 200:
            _LOGGER.error("Token refresh failed: %s", status.get("message", "Unknown error"))
            return False

        token_data = data.get("data", {})
        new_access_token = token_data.get("accessToken")
        new_refresh_token = token_data.get("refreshToken")

        if not new_access_token or not new_refresh_token:
            _LOGGER.error("Token refresh response missing tokens")
            return False

        # IMPORTANT: Both tokens change on refresh!
        self._access_token = new_access_token
        self._refresh_token = new_refresh_token
        self._token_expires_at = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRY_MINUTES)

        _LOGGER.info("Token refresh successful")
        return True

    async def async_ensure_valid_token(self) -> str:
        """Ensure we have a valid access token, refreshing if needed.
        
        Returns:
            Valid access token
            
        Raises:
            DominionEnergyAPIError: If no tokens available or refresh fails
        """
        if not self.has_tokens:
            raise DominionEnergyAPIError("No tokens available - authentication required")

        if self.is_token_expired:
            success = await self.async_refresh_token()
            if not success:
                raise TokenExpiredError("Failed to refresh token")

        return self._access_token

    # ========================================================================
    # 2FA AUTHENTICATION (from dompower/gigya_auth.py)
    # ========================================================================

    async def _gigya_get(self, endpoint: str, params: dict) -> dict:
        """Make a GET request to Gigya API."""
        url = f"{GIGYA_BASE_URL}{endpoint}"
        
        # Add cookies to session if we have them
        if self._cookies:
            for name, value in self._cookies.items():
                self.session.cookie_jar.update_cookies({name: value})
        
        async with self.session.get(url, params=params) as response:
            # Handle text/javascript content type
            text = await response.text()
            return json.loads(text)

    async def _gigya_post(self, endpoint: str, data: dict) -> dict:
        """Make a POST request to Gigya API."""
        url = f"{GIGYA_BASE_URL}{endpoint}"
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
        }
        
        # Add cookies to session if we have them
        if self._cookies:
            for name, value in self._cookies.items():
                self.session.cookie_jar.update_cookies({name: value})
        
        async with self.session.post(url, data=data, headers=headers) as response:
            # Handle text/javascript content type
            text = await response.text()
            return json.loads(text)

    async def async_init_session(self) -> None:
        """Initialize Gigya session (load WAF cookies + bootstrap SDK).
        
        Must be called before async_submit_credentials.
        """
        _LOGGER.debug("Initializing Gigya session")
        
        # Step 0: Load login page for WAF cookies
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://myaccount.dominionenergy.com/",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            ),
        }
        
        async with self.session.get(LOGIN_URL, headers=headers) as response:
            await response.read()
            _LOGGER.debug("WAF cookies obtained")
        
        # Step 1: Bootstrap Gigya SDK
        params = {
            "apiKey": GIGYA_API_KEY,
            "pageURL": LOGIN_URL,
            "sdk": GIGYA_SDK_VERSION,
            "sdkBuild": GIGYA_SDK_BUILD,
            "format": "json",
        }
        
        await self._gigya_get(GIGYA_BOOTSTRAP, params)
        _LOGGER.debug("Gigya bootstrap complete")

    async def async_submit_credentials(self, username: str = None, password: str = None) -> dict:
        """Submit credentials and check if 2FA is required.
        
        Args:
            username: Email (uses self.username if not provided)
            password: Password (uses self.password if not provided)
            
        Returns:
            dict with 'tfa_required' (bool) and 'reg_token' (str if 2FA needed)
            
        Raises:
            InvalidCredentialsError: If credentials are invalid
        """
        username = username or self.username
        password = password or self.password
        
        _LOGGER.debug("Submitting credentials for %s", username)
        
        # Step 2: Login with credentials (POST with all required params)
        data = {
            "loginID": username,
            "password": password,
            "sessionExpiration": "31556952",
            "targetEnv": "jssdk",
            "include": (
                "profile,data,emails,subscriptions,preferences,id_token,groups,loginIDs,"
            ),
            "includeUserInfo": "true",
            "captchaToken": "0",
            "captchaType": "reCaptchaEnterpriseScore",
            "loginMode": "standard",
            "lang": "en",
            "APIKey": GIGYA_API_KEY,
            "source": "showScreenSet",
            "sdk": GIGYA_SDK_VERSION,
            "authMode": "cookie",
            "pageURL": LOGIN_URL,
            "sdkBuild": GIGYA_SDK_BUILD,
            "format": "json",
        }
        
        response = await self._gigya_post(GIGYA_LOGIN, data)
        error_code = response.get("errorCode", 0)
        
        if error_code == GIGYA_ERROR_INVALID_LOGIN:
            raise InvalidCredentialsError("Invalid email address")
        
        if error_code == GIGYA_ERROR_INVALID_PASSWORD:
            raise InvalidCredentialsError("Invalid password")
        
        if error_code == GIGYA_ERROR_TFA_PENDING:
            # 2FA required
            self._reg_token = response.get("regToken")
            _LOGGER.info("2FA required")
            return {"tfa_required": True, "reg_token": self._reg_token}
        
        if error_code != 0:
            raise DominionEnergyAPIError(f"Login failed: {response.get('errorMessage', 'Unknown error')}")
        
        # No 2FA - get tokens directly
        self._gigya_id_token = response.get("id_token")
        self._gigya_uid = response.get("UID")
        
        return {"tfa_required": False}

    async def async_get_tfa_options(self) -> list[TFATarget]:
        """Get available 2FA options (phone numbers or emails).
        
        Returns:
            List of TFATarget objects
            
        Raises:
            DominionEnergyAPIError: If getting options fails
        """
        if not self._reg_token:
            raise DominionEnergyAPIError("No reg_token - call async_submit_credentials first")
        
        _LOGGER.debug("Getting 2FA providers")
        
        # Get providers
        params = {
            "regToken": self._reg_token,
            "APIKey": GIGYA_API_KEY,
            "sdk": GIGYA_SDK_VERSION,
            "pageURL": LOGIN_URL,
            "sdkBuild": GIGYA_SDK_BUILD,
            "format": "json",
        }
        
        response = await self._gigya_get(GIGYA_TFA_PROVIDERS, params)
        
        _LOGGER.error("DEBUG: TFA providers full response: %s", json.dumps(response, indent=2))
        
        if response.get("errorCode") != 0:
            _LOGGER.error("TFA providers request failed - errorCode: %s, errorMessage: %s", 
                         response.get("errorCode"), response.get("errorMessage"))
            raise DominionEnergyAPIError(f"Failed to get TFA providers: {response.get('errorMessage')}")
        
        active_providers = response.get("activeProviders", [])
        _LOGGER.error("DEBUG: Active TFA providers: %s", active_providers)
        
        # Extract provider names from dict format: [{"name": "gigyaPhone"}, ...]
        provider_names = [p.get("name") for p in active_providers if isinstance(p, dict)]
        _LOGGER.error("DEBUG: Provider names extracted: %s", provider_names)
        
        # Initialize TFA with phone (preferred)
        if "gigyaPhone" in provider_names:
            _LOGGER.error("DEBUG: gigyaPhone found in active providers, initializing...")
            
            init_params = {
                "provider": TFAProvider.PHONE.value,  # Use enum value
                "mode": "verify",
                "regToken": self._reg_token,
                "APIKey": GIGYA_API_KEY,
                "sdk": GIGYA_SDK_VERSION,
                "pageURL": LOGIN_URL,
                "sdkBuild": GIGYA_SDK_BUILD,
                "format": "json",
            }
            
            _LOGGER.error("DEBUG: TFA init params: %s", init_params)
            
            init_response = await self._gigya_get(GIGYA_TFA_INIT, init_params)
            
            _LOGGER.error("DEBUG: TFA init full response: %s", json.dumps(init_response, indent=2))
            
            if init_response.get("errorCode") != 0:
                _LOGGER.error("Failed to init phone TFA - errorCode: %s, errorMessage: %s",
                             init_response.get("errorCode"), init_response.get("errorMessage"))
                raise DominionEnergyAPIError(f"Failed to init phone TFA: {init_response.get('errorMessage')}")
            
            self._gigya_assertion = init_response.get("gigyaAssertion")
            _LOGGER.error("DEBUG: Got gigya_assertion: %s...", self._gigya_assertion[:20] if self._gigya_assertion else "None")
            
            # Get phone numbers
            phone_params = {
                "gigyaAssertion": self._gigya_assertion,
                "APIKey": GIGYA_API_KEY,
                "sdk": GIGYA_SDK_VERSION,
                "pageURL": LOGIN_URL,
                "sdkBuild": GIGYA_SDK_BUILD,
                "format": "json",
            }
            
            _LOGGER.error("DEBUG: Phone numbers request params: %s", phone_params)
            
            phone_response = await self._gigya_get(GIGYA_TFA_PHONE_NUMBERS, phone_params)
            
            _LOGGER.error("DEBUG: Phone numbers full response: %s", json.dumps(phone_response, indent=2))
            
            if phone_response.get("errorCode") == 0:
                phones = phone_response.get("phones", [])
                _LOGGER.error("DEBUG: Found %d phone(s): %s", len(phones), phones)
                targets = []
                for phone in phones:
                    target = TFATarget(
                        provider=TFAProvider.PHONE,
                        target=phone.get("obfuscated", "Unknown"),
                        id=phone.get("id", "")
                    )
                    _LOGGER.error("DEBUG: Created target: provider=%s, target=%s, id=%s", 
                                 target.provider, target.target, target.id)
                    targets.append(target)
                
                if targets:
                    _LOGGER.error("DEBUG: Returning %d phone number(s) for 2FA", len(targets))
                    return targets
                else:
                    _LOGGER.error("DEBUG: Phones array was empty!")
            else:
                _LOGGER.error("Phone numbers request failed - errorCode: %s, errorMessage: %s",
                             phone_response.get("errorCode"), phone_response.get("errorMessage"))
        else:
            _LOGGER.error("DEBUG: gigyaPhone NOT in active providers!")
        
        # Fallback to email if phone not available
        if "gigyaEmail" in provider_names:
            _LOGGER.error("DEBUG: gigyaEmail found but not implemented yet")
        
        _LOGGER.error("DEBUG: About to raise 'No 2FA options available'")
        raise DominionEnergyAPIError("No 2FA options available")

    async def async_send_tfa_code(self, target: TFATarget) -> bool:
        """Send 2FA code to the specified target.
        
        Args:
            target: TFATarget from async_get_tfa_options()
            
        Returns:
            True if code sent successfully
        """
        if not self._gigya_assertion:
            raise DominionEnergyAPIError("No gigya_assertion - call async_get_tfa_options first")
        
        self._tfa_target = target
        
        _LOGGER.debug("Sending 2FA code to %s", target.target)
        
        if target.provider == TFAProvider.PHONE:
            params = {
                "gigyaAssertion": self._gigya_assertion,
                "phoneID": target.id,
                "method": "sms",
                "lang": "en",
                "regToken": self._reg_token,
                "APIKey": GIGYA_API_KEY,
                "sdk": GIGYA_SDK_VERSION,
                "pageURL": LOGIN_URL,
                "sdkBuild": GIGYA_SDK_BUILD,
                "format": "json",
            }
            
            response = await self._gigya_get(GIGYA_TFA_SEND_PHONE, params)
            
            if response.get("errorCode") != 0:
                raise DominionEnergyAPIError(f"Failed to send SMS: {response.get('errorMessage')}")
            
            self._phv_token = response.get("phvToken")
            
        else:  # Email
            # Email implementation...
            raise DominionEnergyAPIError("Email 2FA not implemented yet")
        
        _LOGGER.info("2FA code sent to %s", target.target)
        return True

    async def async_verify_tfa_code(self, code: str) -> TokenPair:
        """Verify 2FA code and complete authentication.
        
        Args:
            code: 6-digit verification code
            
        Returns:
            TokenPair with access and refresh tokens
            
        Raises:
            TFAVerificationError: If code is invalid
        """
        if not self._gigya_assertion:
            raise DominionEnergyAPIError("No gigya_assertion - call async_send_tfa_code first")
        
        _LOGGER.debug("Verifying 2FA code")
        
        target = self._tfa_target
        
        if target and target.provider == TFAProvider.PHONE:
            # Phone verification
            params = {
                "gigyaAssertion": self._gigya_assertion,
                "phvToken": self._phv_token,
                "code": code,
                "regToken": self._reg_token,
                "APIKey": GIGYA_API_KEY,
                "sdk": GIGYA_SDK_VERSION,
                "pageURL": LOGIN_URL,
                "sdkBuild": GIGYA_SDK_BUILD,
                "format": "json",
            }
            
            response = await self._gigya_get(GIGYA_TFA_VERIFY_PHONE, params)
        else:
            raise DominionEnergyAPIError("Email 2FA not implemented")
        
        error_code = response.get("errorCode", 0)
        
        if error_code == GIGYA_ERROR_INVALID_JWT:
            raise TFAVerificationError("TFA session expired - please restart login")
        
        if error_code != 0:
            raise TFAVerificationError(f"Invalid code: {response.get('errorMessage', 'Unknown error')}")
        
        provider_assertion = response.get("providerAssertion", "")
        
        # Finalize TFA
        finalize_params = {
            "gigyaAssertion": self._gigya_assertion,
            "providerAssertion": provider_assertion,
            "regToken": self._reg_token,
            "APIKey": GIGYA_API_KEY,
            "sdk": GIGYA_SDK_VERSION,
            "pageURL": LOGIN_URL,
            "sdkBuild": GIGYA_SDK_BUILD,
            "format": "json",
        }
        
        await self._gigya_get(GIGYA_TFA_FINALIZE, finalize_params)
        
        # Finalize registration
        reg_params = {
            "regToken": self._reg_token,
            "APIKey": GIGYA_API_KEY,
            "sdk": GIGYA_SDK_VERSION,
            "pageURL": LOGIN_URL,
            "sdkBuild": GIGYA_SDK_BUILD,
            "format": "json",
        }
        
        reg_response = await self._gigya_get(GIGYA_FINALIZE_REGISTRATION, reg_params)
        
        # Get account info with id_token
        account_params = {
            "include": "id_token",
            "regToken": self._reg_token,
            "APIKey": GIGYA_API_KEY,
            "sdk": GIGYA_SDK_VERSION,
            "pageURL": LOGIN_URL,
            "sdkBuild": GIGYA_SDK_BUILD,
            "format": "json",
        }
        
        account_response = await self._gigya_get(GIGYA_ACCOUNT_INFO, account_params)
        
        self._gigya_id_token = account_response.get("id_token")
        self._gigya_uid = account_response.get("UID")
        
        if not self._gigya_id_token:
            raise DominionEnergyAPIError("Failed to get id_token after 2FA")
        
        _LOGGER.info("2FA verification successful")
        
        # Exchange Gigya token for Dominion tokens
        return await self._async_exchange_for_dominion_tokens()

    async def _async_exchange_for_dominion_tokens(self) -> TokenPair:
        """Exchange Gigya id_token for Dominion API access/refresh tokens."""
        _LOGGER.debug("Exchanging Gigya token for Dominion tokens")
        
        url = f"{BASE_URL}{ENDPOINT_LOGIN}"
        headers = DEFAULT_HEADERS.copy()
        
        payload = {
            "idToken": self._gigya_id_token,
            "UUID": str(uuid.uuid4()),
        }
        
        async with self.session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                text = await response.text()
                raise DominionEnergyAPIError(f"Token exchange failed: {response.status} - {text}")
            
            data = await response.json()
        
        status = data.get("status", {})
        if status.get("code") != 200:
            raise DominionEnergyAPIError(f"Token exchange failed: {status.get('message')}")
        
        token_data = data.get("data", {})
        access_token = token_data.get("accessToken")
        refresh_token = token_data.get("refreshToken")
        
        if not access_token or not refresh_token:
            raise DominionEnergyAPIError("Token exchange response missing tokens")
        
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._token_expires_at = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRY_MINUTES)
        
        _LOGGER.info("Successfully obtained Dominion API tokens")
        
        return TokenPair(access_token, refresh_token, self._token_expires_at)

    # ========================================================================
    # COOKIE MANAGEMENT (for 2FA bypass)
    # ========================================================================

    def export_cookies(self) -> dict[str, str]:
        """Export cookies for storage in HA config."""
        cookies = {}
        for cookie in self.session.cookie_jar:
            # Only save relevant cookies
            if any(x in cookie.key for x in ("gmid", "ucid", "incap", "visid", "gig_")):
                cookies[cookie.key] = cookie.value
        return cookies

    def import_cookies(self, cookies: dict[str, str]) -> None:
        """Import cookies from HA config."""
        self._cookies = cookies
        for name, value in cookies.items():
            self.session.cookie_jar.update_cookies({name: value})

    # ========================================================================
    # ACCOUNT & USAGE DATA
    # ========================================================================

    async def async_get_account_info(self) -> dict[str, Any]:
        """Get account information."""
        token = await self.async_ensure_valid_token()
        
        url = f"{BASE_URL}{ENDPOINT_ACCOUNTS}"
        headers = {
            **DEFAULT_HEADERS,
            "Authorization": f"Bearer {token}",
        }
        
        async with self.session.get(url, headers=headers) as response:
            if response.status != 200:
                text = await response.text()
                raise DominionEnergyAPIError(f"Failed to get account info: {response.status} - {text}")
            
            data = await response.json()
        
        # Extract account details
        accounts_data = data.get("data", {}).get("accounts", [])
        if accounts_data:
            account = accounts_data[0]
            self._account_number = account.get("accountNumber")
            self._customer_number = account.get("bpNumber")
            
            contracts = account.get("contracts", [])
            if contracts:
                self._meter_number = contracts[0].get("meterNumber")
        
        return data

    async def async_get_usage(
        self,
        account_number: str = None,
        meter_number: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
    ) -> dict[str, Any]:
        """Get usage data."""
        token = await self.async_ensure_valid_token()
        
        account = account_number or self._account_number
        meter = meter_number or self._meter_number
        
        if not account or not meter:
            raise DominionEnergyAPIError("Account and meter numbers required")
        
        if not start_date:
            start_date = datetime.now() - timedelta(days=7)
        if not end_date:
            end_date = datetime.now()
        
        url = f"{BASE_URL}{ENDPOINT_USAGE}"
        headers = {
            **DEFAULT_HEADERS,
            "Authorization": f"Bearer {token}",
        }
        
        params = {
            "accountNumber": account,
            "meterNumber": meter,
            "fromDate": start_date.strftime("%Y-%m-%d"),
            "toDate": end_date.strftime("%Y-%m-%d"),
        }
        
        async with self.session.get(url, headers=headers, params=params) as response:
            if response.status != 200:
                text = await response.text()
                raise DominionEnergyAPIError(f"Failed to get usage: {response.status} - {text}")
            
            return await response.json()
