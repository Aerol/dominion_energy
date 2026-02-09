"""API Client for Dominion Energy Virginia."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any
from datetime import datetime, timedelta
from urllib.parse import urlencode

import aiohttp

from .const import (
    GIGYA_API_KEY,
    GIGYA_LOGIN_URL,
    TOKEN_URL,
    USAGE_ELECTRIC_URL,
    USAGE_HOURLY_URL,
    ACCOUNT_DETAILS_URL,
    ACCOUNT_INFO_URL,
    BILLING_URL,
)

_LOGGER = logging.getLogger(__name__)


class DominionEnergyAPIError(Exception):
    """Exception for Dominion Energy API errors."""


class DominionEnergyAPI:
    """API client for Dominion Energy Virginia."""

    def __init__(self, username: str, password: str, session: aiohttp.ClientSession, gigya_login_token: str = None) -> None:
        """Initialize the API client."""
        self.username = username
        self.password = password
        self.session = session
        self._gigya_login_token = gigya_login_token
        self._gigya_id_token = None
        self._gigya_uid = None
        self._bearer_token = None
        self._account_number = None
        self._customer_number = None
        self._meter_number = None

    async def async_get_jwt_from_gigya_token(self) -> bool:
        """Use Gigya login token to get a JWT without re-authenticating."""
        try:
            # Use accounts.getJWT with the login token
            params = {
                "login_token": self._gigya_login_token,
                "fields": "profile,data,emails",
                "APIKey": GIGYA_API_KEY,
                "format": "json",
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "*/*",
                "Origin": "https://login.dominionenergy.com",
                "Referer": "https://login.dominionenergy.com/",
            }
            
            # Try accounts.getJWT endpoint
            async with self.session.get(
                f"{GIGYA_LOGIN_URL.replace('accounts.login', 'accounts.getJWT')}",
                params=params,
                headers=headers,
            ) as response:
                response_text = await response.text()
                _LOGGER.debug("Gigya getJWT response status: %s", response.status)
                
                try:
                    gigya_response = json.loads(response_text)
                except json.JSONDecodeError:
                    _LOGGER.error("Failed to parse Gigya JWT response")
                    return False
                
                if gigya_response.get("errorCode") == 0:
                    # Success! Extract the ID token
                    self._gigya_id_token = gigya_response.get("id_token")
                    self._gigya_uid = gigya_response.get("UID")
                    
                    if self._gigya_id_token:
                        _LOGGER.info("Successfully obtained JWT using Gigya login token")
                        # Now exchange for Dominion token
                        return await self._exchange_gigya_token_for_dominion_token()
                
                _LOGGER.error("Gigya getJWT failed - Error Code: %s", gigya_response.get("errorCode"))
                return False
                
        except Exception as err:
            _LOGGER.exception("Error using Gigya login token: %s", err)
            return False

    async def _exchange_gigya_token_for_dominion_token(self) -> bool:
        """Exchange Gigya id_token for Dominion API bearer token."""
        try:
            # The Dominion API likely has an endpoint that accepts the Gigya id_token
            # and returns their own JWT. Common endpoints:
            # /UsermanagementAPI/api/1/Login/auth
            # /api/auth/token
            
            headers = {
                "Authorization": f"Bearer {self._gigya_id_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Origin": "https://myaccount.dominionenergy.com",
                "Referer": "https://myaccount.dominionenergy.com/",
            }
            
            # Try the login/auth endpoint
            auth_url = "https://prodsvc-dominioncip.smartcmobile.com/UsermanagementAPI/api/1/Login/auth"
            
            async with self.session.post(
                auth_url,
                headers=headers,
                json={"idToken": self._gigya_id_token}
            ) as response:
                _LOGGER.debug("Token exchange response status: %s", response.status)
                
                if response.status == 200:
                    data = await response.json()
                    # The response might contain the bearer token
                    # Check for common field names
                    token = (
                        data.get("token") or
                        data.get("accessToken") or
                        data.get("access_token") or
                        data.get("bearerToken") or
                        data.get("jwt")
                    )
                    
                    if token:
                        self._bearer_token = token
                        _LOGGER.info("Successfully exchanged Gigya token for Dominion token")
                        return True
                    else:
                        _LOGGER.warning("Token exchange succeeded but no token found in response: %s", data)
                else:
                    error_text = await response.text()
                    _LOGGER.error("Token exchange failed: %s - %s", response.status, error_text[:200])
            
            # Fallback: Just use the Gigya id_token (probably won't work)
            _LOGGER.warning("Using Gigya id_token as bearer token (may not work)")
            self._bearer_token = self._gigya_id_token
            return True
            
        except Exception as err:
            _LOGGER.exception("Error exchanging tokens: %s", err)
            # Fallback
            self._bearer_token = self._gigya_id_token
            return True

    async def async_login(self) -> bool:
        """Login to Dominion Energy via Gigya and obtain tokens with 2FA support."""
        # If we have a Gigya login token, try to use it first
        if self._gigya_login_token:
            _LOGGER.debug("Attempting to get JWT using Gigya login token")
            if await self.async_get_jwt_from_gigya_token():
                return True
            _LOGGER.warning("Failed to use Gigya login token, falling back to password login")
        
        try:
            # Step 1: Login to Gigya
            login_data = {
                "loginID": self.username,
                "password": self.password,
                "sessionExpiration": "86400",  # 24 hours
                "include": "profile,data,emails,id_token",
                "includeUserInfo": "true",
                "APIKey": GIGYA_API_KEY,
                "format": "json",
            }
            
            _LOGGER.debug("Attempting Gigya login for user: %s", self.username)
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://login.dominionenergy.com",
                "Referer": "https://login.dominionenergy.com/",
            }
            
            async with self.session.post(
                GIGYA_LOGIN_URL,
                data=urlencode(login_data),
                headers=headers
            ) as response:
                text = await response.text()
                _LOGGER.debug("Gigya response status: %s", response.status)
                
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as err:
                    _LOGGER.error("Failed to parse Gigya response: %s. Response text: %s", err, text[:200])
                    return False
                
                error_code = data.get("errorCode", 0)
                
                # Check for 2FA required
                if error_code == 403101:
                    _LOGGER.info("2FA required (error 403101)")
                    reg_token = data.get("regToken")
                    if not reg_token:
                        _LOGGER.error("2FA required but no regToken received")
                        return False
                    
                    # We can't complete 2FA in async_login - need user input
                    # Raise special exception that config_flow can catch
                    raise DominionEnergyAPIError(f"2FA_REQUIRED:{reg_token}")
                
                # Check for other errors
                elif error_code != 0:
                    _LOGGER.error(
                        "Gigya login failed - Error Code: %s, Reason: %s",
                        error_code, data.get("statusReason", "Unknown")
                    )
                    if "errorDetails" in data:
                        _LOGGER.error("Error details: %s", data["errorDetails"])
                    
                    if error_code == 400006:
                        _LOGGER.error(
                            "Gigya bot detection triggered. Use manual token method instead."
                        )
                    return False
                
                # Login successful without 2FA
                self._gigya_id_token = data.get("id_token")
                self._gigya_uid = data.get("UID")
                
                if not self._gigya_id_token or not self._gigya_uid:
                    _LOGGER.error("Missing id_token or UID from Gigya response")
                    return False
            
            # Exchange Gigya token for Dominion bearer token
            await self._exchange_gigya_token_for_dominion_token()
            
            # Get account information
            await self._get_account_info()
            
            return True
                    
        except DominionEnergyAPIError:
            # Re-raise our own exceptions
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("Error during login: %s", err)
            raise DominionEnergyAPIError(f"Login failed: {err}") from err
    
    async def complete_2fa_login(self, reg_token: str, code: str) -> bool:
        """Complete 2FA authentication with user-provided code."""
        try:
            _LOGGER.info("Starting 2FA flow with provided code")
            
            # Step 1: Initialize phone 2FA
            init_url = "https://auth.dominionenergy.com/accounts.tfa.initTFA"
            params = {
                "provider": "gigyaPhone",
                "mode": "verify",
                "regToken": reg_token,
                "APIKey": GIGYA_API_KEY,
                "format": "json",
            }
            
            async with self.session.get(init_url, params=params) as response:
                init_data = await response.json()
                if init_data.get("errorCode") != 0:
                    _LOGGER.error("Failed to init phone 2FA: %s", init_data)
                    return False
                
                gigya_assertion = init_data.get("gigyaAssertion")
                _LOGGER.debug("Phone 2FA initialized")
            
            # Step 2: Get registered phones
            phones_url = "https://auth.dominionenergy.com/accounts.tfa.phone.getRegisteredPhoneNumbers"
            params = {"gigyaAssertion": gigya_assertion, "APIKey": GIGYA_API_KEY, "format": "json"}
            
            async with self.session.get(phones_url, params=params) as response:
                phones_data = await response.json()
                if phones_data.get("errorCode") != 0:
                    _LOGGER.error("Failed to get phones: %s", phones_data)
                    return False
                
                phones = phones_data.get("phones", [])
                if not phones:
                    _LOGGER.error("No registered phone numbers found")
                    return False
                
                phone_id = phones[0]["id"]
                _LOGGER.debug("Found registered phone")
            
            # Step 3: Send SMS code
            send_url = "https://auth.dominionenergy.com/accounts.tfa.phone.sendVerificationCode"
            params = {
                "gigyaAssertion": gigya_assertion,
                "phoneID": phone_id,
                "method": "sms",
                "lang": "en",
                "regToken": reg_token,
                "APIKey": GIGYA_API_KEY,
                "format": "json",
            }
            
            async with self.session.get(send_url, params=params) as response:
                send_data = await response.json()
                if send_data.get("errorCode") != 0:
                    _LOGGER.error("Failed to send SMS: %s", send_data)
                    return False
                
                _LOGGER.info("SMS code sent")
            
            # Step 4: Verify the code
            verify_url = "https://auth.dominionenergy.com/accounts.tfa.phone.completeVerification"
            params = {
                "gigyaAssertion": gigya_assertion,
                "vToken": code,
                "regToken": reg_token,
                "APIKey": GIGYA_API_KEY,
                "format": "json",
            }
            
            async with self.session.get(verify_url, params=params) as response:
                verify_data = await response.json()
                if verify_data.get("errorCode") != 0:
                    _LOGGER.error("2FA code verification failed: %s", verify_data)
                    return False
                
                _LOGGER.info("2FA code verified")
            
            # Step 5: Finalize 2FA
            finalize_url = "https://auth.dominionenergy.com/accounts.tfa.finalizeTFA"
            params = {"gigyaAssertion": gigya_assertion, "APIKey": GIGYA_API_KEY, "format": "json"}
            
            async with self.session.get(finalize_url, params=params) as response:
                finalize_data = await response.json()
                if finalize_data.get("errorCode") != 0:
                    _LOGGER.error("Failed to finalize 2FA: %s", finalize_data)
                    return False
                
                _LOGGER.info("2FA finalized")
            
            # Step 6: Finalize registration
            reg_finalize_url = "https://auth.dominionenergy.com/accounts.finalizeRegistration"
            params = {"regToken": reg_token, "APIKey": GIGYA_API_KEY, "format": "json"}
            
            async with self.session.get(reg_finalize_url, params=params) as response:
                reg_data = await response.json()
                if reg_data.get("errorCode") != 0:
                    _LOGGER.error("Failed to finalize registration: %s", reg_data)
                    return False
                
                _LOGGER.info("Registration finalized")
            
            # Step 7: Get account info with id_token
            account_url = "https://auth.dominionenergy.com/accounts.getAccountInfo"
            data_params = {
                "include": "groups,profile,data,id_token",
                "lang": "en",
                "APIKey": GIGYA_API_KEY,
                "sdk": "js_latest",
                "authMode": "cookie",
                "format": "json",
            }
            
            async with self.session.post(account_url, data=urlencode(data_params)) as response:
                account_data = await response.json()
                if account_data.get("errorCode") != 0:
                    _LOGGER.error("Failed to get account info: %s", account_data)
                    return False
                
                self._gigya_id_token = account_data.get("id_token")
                self._gigya_uid = account_data.get("UID")
                
                if not self._gigya_id_token:
                    _LOGGER.error("No id_token in account info")
                    return False
                
                _LOGGER.info("2FA flow complete, got id_token")
            
            # Exchange for Dominion token
            await self._exchange_gigya_token_for_dominion_token()
            
            # Get account information
            await self._get_account_info()
            
            return True
                
        except Exception as err:
            _LOGGER.exception("Error completing 2FA: %s", err)
            return False

    async def _get_account_info(self) -> None:
        """Fetch account and meter information."""
        try:
            headers = self._get_headers()
            
            # This endpoint requires account number, but we need to get it first
            # In practice, the account number might be stored in Gigya data
            # For now, we'll try to extract it from subsequent calls
            _LOGGER.debug("Account info retrieval deferred until first usage call")
            
        except Exception as err:
            _LOGGER.warning("Could not fetch account info: %s", err)

    def _get_headers(self, include_account: bool = False) -> dict[str, str]:
        """Get standard headers for API requests."""
        headers = {
            "Authorization": f"Bearer {self._bearer_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": "https://myaccount.dominionenergy.com",
            "Referer": "https://myaccount.dominionenergy.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,PUT,POST,DELETE,PATCH,OPTIONS",
            "uid": "1",
            "pt": "1",
            "ReferenceId": f"MM-{uuid.uuid4()}",
            "channel": "WEB",
        }
        
        if include_account:
            if self._account_number:
                # Mask account number: show last 7 digits (e.g., *****8858444)
                masked_account = f"*****{self._account_number[-7:]}"
                headers["accountNumber"] = masked_account
                _LOGGER.debug("Added masked accountNumber header: %s", masked_account)
            
            if self._customer_number:
                # Mask customer number: show last 5 digits (e.g., *****16540)
                masked_customer = f"*****{self._customer_number[-5:]}"
                headers["customerNumber"] = masked_customer
                _LOGGER.debug("Added masked customerNumber header: %s", masked_customer)
        
        return headers

    async def async_get_usage_data(self) -> dict[str, Any]:
        """Fetch energy usage data from Dominion Energy."""
        _LOGGER.debug("async_get_usage_data called - bearer_token present: %s", bool(self._bearer_token))
        
        # Only attempt login if we don't already have a bearer token (manual token mode)
        if not self._bearer_token:
            # Check if we have credentials for automatic login
            if not self.username or not self.password:
                _LOGGER.error("No bearer token and no username/password configured - cannot fetch data")
                raise DominionEnergyAPIError("Authentication not configured")
            
            _LOGGER.debug("No bearer token found, attempting login")
            login_success = await self.async_login()
            if not login_success:
                raise DominionEnergyAPIError("Authentication failed")
        else:
            _LOGGER.debug("Using existing bearer token (manual token mode) - token length: %d", len(self._bearer_token))
        
        try:
            # Get monthly usage data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365)  # Last year
            
            if not self._account_number or not self._meter_number:
                _LOGGER.error("Missing account number or meter number")
                raise DominionEnergyAPIError("Account information not configured")
            
            params = {
                "AccountNumber": self._account_number,
                "MeterNumber": self._meter_number,
                "From": start_date.strftime("%Y-%m-%d"),
                "To": end_date.strftime("%Y-%m-%d"),
                "Uom": "kWh",
                "Periodicity": "MO",  # Monthly data
            }
            
            _LOGGER.debug("Fetching usage data for account %s", self._account_number)
            
            headers = self._get_headers(include_account=True)
            
            async with self.session.get(
                USAGE_ELECTRIC_URL,
                headers=headers,
                params=params
            ) as response:
                if response.status == 401:
                    # Token expired, re-login
                    await self.async_login()
                    return await self.async_get_usage_data()
                
                if response.status == 200:
                    monthly_data = await response.json()
                else:
                    # Log the full error response
                    error_text = await response.text()
                    _LOGGER.error(
                        "Failed to get usage data: %s - %s. URL: %s, Headers: %s, Response: %s",
                        response.status, response.reason, USAGE_ELECTRIC_URL, 
                        {k: v for k, v in headers.items() if k != "Authorization"},
                        error_text[:500]
                    )
                    raise DominionEnergyAPIError(f"Failed to get usage data: {response.status}")
            
            # Also get today's hourly data
            # Temporarily disabled - causing authentication issues
            hourly_data = []
            # hourly_data = await self.async_get_hourly_usage(datetime.now())
            
            # Parse and combine the data
            return self._parse_usage_data(monthly_data, hourly_data)
                    
        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching usage data: %s", err)
            raise DominionEnergyAPIError(f"Failed to fetch usage data: {err}") from err

    async def async_get_hourly_usage(self, date: datetime) -> list[dict]:
        """Fetch hourly usage data for a specific date."""
        try:
            params = {
                "accountNumber": self._account_number,
                "ActionCode": "4",  # Hourly data
                "StartDate": date.strftime("%Y-%m-%d"),
                "EndDate": (date + timedelta(days=1)).strftime("%Y-%m-%d"),
            }
            
            headers = self._get_headers(include_account=True)
            
            async with self.session.get(
                USAGE_HOURLY_URL,
                headers=headers,
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status", {}).get("type") == "success":
                        hourly_usages = data.get("data", {}).get("electricUsages", [])
                        _LOGGER.debug("Retrieved %d hourly readings", len(hourly_usages))
                        return hourly_usages
                else:
                    _LOGGER.warning("Failed to get hourly usage: %s", response.status)
                return []
                
        except Exception as err:
            _LOGGER.warning("Error fetching hourly usage: %s", err)
            return []

    async def async_get_billing_info(self) -> dict[str, Any] | None:
        """Fetch current billing information."""
        try:
            if not self._account_number:
                return None
            
            # Get the most recent invoice
            params = {
                "invoiceId": "",  # Empty to get latest
                "accountNumber": self._account_number,
            }
            
            headers = self._get_headers(include_account=True)
            
            async with self.session.get(
                BILLING_URL,
                headers=headers,
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status", {}).get("type") == "success":
                        billing_data = data.get("data", {})
                        results = billing_data.get("zBillInvHeadtoItemNav", {}).get("results", [])
                        if results:
                            return results[0]  # Most recent bill
                return None
                
        except Exception as err:
            _LOGGER.warning("Error fetching billing info: %s", err)
            return None

    def _parse_usage_data(self, raw_data: dict, hourly_data: list[dict] = None) -> dict[str, Any]:
        """Parse the raw API response into usable data."""
        result = raw_data.get("Result", {})
        usages = result.get("electricUsages", [])
        
        # Extract account and meter info from first record
        if usages and not self._account_number:
            self._account_number = usages[0].get("accountNumber")
            self._meter_number = usages[0].get("meterNumber")
        
        # Get the most recent month's data
        latest = usages[-1] if usages else {}
        
        # Calculate totals
        monthly_consumption = sum(float(u.get("consumption", 0)) for u in usages[-1:])
        monthly_cost = sum(float(u.get("amount", 0)) for u in usages[-1:])
        
        # Estimate daily usage from most recent month
        days_in_period = 30  # Approximate
        daily_usage = monthly_consumption / days_in_period if monthly_consumption > 0 else 0
        
        # Get the most recent hourly reading
        last_hour_usage = 0
        last_hour_time = None
        if hourly_data and len(hourly_data) > 0:
            # Sort by date and get the most recent
            try:
                sorted_data = sorted(
                    hourly_data,
                    key=lambda x: datetime.strptime(x.get("readDate", "1/1/2000 12:00:00 AM"), "%m/%d/%Y %I:%M:%S %p"),
                    reverse=True
                )
                if sorted_data:
                    most_recent = sorted_data[0]
                    last_hour_usage = float(most_recent.get("consumption", 0))
                    last_hour_time = most_recent.get("readDate")
                    _LOGGER.debug("Most recent hourly reading: %s kWh at %s", last_hour_usage, last_hour_time)
            except (ValueError, AttributeError) as err:
                _LOGGER.warning("Error parsing hourly data: %s", err)
        
        return {
            "last_hour_usage": round(last_hour_usage, 3),
            "last_hour_reading_time": last_hour_time,
            "daily_usage": round(daily_usage, 2),
            "monthly_usage": round(monthly_consumption, 2),
            "estimated_cost": round(monthly_cost, 2),
            "peak_demand": 0,  # Not in this API response
            "last_updated": datetime.now().isoformat(),
            "account_number": self._account_number,
            "meter_number": self._meter_number,
        }
