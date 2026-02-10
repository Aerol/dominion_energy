"""The Dominion Energy Virginia integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DominionEnergyAPI, DominionEnergyAPIError, TokenExpiredError
from .const import DOMAIN, CONF_MANUAL_TOKEN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dominion Energy Virginia from a config entry."""
    session = async_get_clientsession(hass)
    auth_method = entry.data.get("auth_method", "manual_token")

    if auth_method == "automatic":
        # Automatic authentication with tokens
        username = entry.data[CONF_USERNAME]
        password = entry.data[CONF_PASSWORD]
        access_token = entry.data.get("access_token")
        refresh_token = entry.data.get("refresh_token")

        api = DominionEnergyAPI(
            username=username,
            password=password,
            session=session,
            access_token=access_token,
            refresh_token=refresh_token,
        )

        # Import cookies if available (for 2FA bypass)
        cookies = entry.data.get("cookies", {})
        if cookies:
            api.import_cookies(cookies)

        # Set account numbers from config
        api._account_number = entry.data.get("account_number")
        api._customer_number = entry.data.get("customer_number")
        api._meter_number = entry.data.get("meter_number")

        # Ensure token is valid (will auto-refresh if needed)
        try:
            await api.async_ensure_valid_token()
            _LOGGER.info("Token validated successfully")

            # If token was refreshed, update config entry
            if api._access_token != access_token:
                hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        "access_token": api._access_token,
                        "refresh_token": api._refresh_token,
                    },
                )
                _LOGGER.info("Tokens refreshed and saved")

        except TokenExpiredError:
            _LOGGER.error("Tokens expired - re-authentication required")
            return False
        except DominionEnergyAPIError as e:
            _LOGGER.error("Failed to validate token: %s", e)
            return False

        # Get account info (optional - integration can work without it)
        try:
            await api.async_get_account_info()
            _LOGGER.info("Account info retrieved successfully")
        except DominionEnergyAPIError as e:
            _LOGGER.warning("Could not get account info (not critical): %s", e)
            # Continue anyway - tokens work fine

    else:
        # Manual token method
        manual_token = entry.data[CONF_MANUAL_TOKEN]
        account_number = entry.data["account_number"]
        customer_number = entry.data["customer_number"]
        meter_number = entry.data["meter_number"]

        api = DominionEnergyAPI(
            username="",
            password="",
            session=session,
            access_token=manual_token,
            refresh_token=None,
        )

        api._account_number = account_number
        api._customer_number = customer_number
        api._meter_number = meter_number

    # Create data update coordinator
    coordinator = DominionEnergyDataUpdateCoordinator(hass, api)

    # Fetch initial data so sensors have something to display
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class DominionEnergyDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Dominion Energy data."""

    def __init__(self, hass: HomeAssistant, api: DominionEnergyAPI) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=30),
        )
        self.api = api

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            # Ensure token is valid (auto-refresh if needed)
            if self.api.has_tokens:
                await self.api.async_ensure_valid_token()

            # Fetch usage data
            _LOGGER.error("DEBUG: Fetching usage data with account=%s, meter=%s", 
                         self.api._account_number, self.api._meter_number)
            
            raw_data = await self.api.async_get_usage()
            
            _LOGGER.error("DEBUG: Raw usage data response keys: %s", list(raw_data.keys()) if isinstance(raw_data, dict) else type(raw_data))

            # Parse the response into sensor data
            parsed_data = {
                "account_number": self.api._account_number,
                "meter_number": self.api._meter_number,
                "last_hour_usage": 0,
                "last_hour_reading_time": None,
                "daily_usage": 0,
                "monthly_usage": 0,
                "estimated_cost": 0,
            }
            
            # Check if we got JSON data
            if raw_data and isinstance(raw_data, dict) and "raw_data" not in raw_data:
                _LOGGER.error("DEBUG: Processing JSON response")
                _LOGGER.error("DEBUG: Response structure: %s", raw_data)
                
                # Try to find the data section
                data_section = raw_data.get("data", raw_data)
                
                if "intervals" in data_section or "usage" in data_section:
                    # Standard format
                    intervals = data_section.get("intervals", data_section.get("usage", []))
                    _LOGGER.error("DEBUG: Found %d intervals/usage items", len(intervals))
                    
                    if intervals:
                        _LOGGER.error("DEBUG: First interval: %s", intervals[0])
                        _LOGGER.error("DEBUG: Last interval: %s", intervals[-1])
                        
                        total = 0
                        for item in intervals:
                            val = item.get("value", item.get("consumption", item.get("usage", 0)))
                            try:
                                total += float(val)
                            except (ValueError, TypeError):
                                pass
                        
                        last = intervals[-1]
                        parsed_data["last_hour_usage"] = float(last.get("value", last.get("consumption", last.get("usage", 0))))
                        parsed_data["last_hour_reading_time"] = last.get("timestamp", last.get("date", last.get("readingDateTime")))
                        parsed_data["daily_usage"] = total
                        parsed_data["monthly_usage"] = total
                        parsed_data["estimated_cost"] = round(total * 0.12, 2)
                        
                        _LOGGER.info("Parsed %d usage readings, total: %.2f kWh", len(intervals), total)
                else:
                    _LOGGER.error("DEBUG: Unknown JSON structure, keys: %s", list(data_section.keys()))
            else:
                _LOGGER.error("DEBUG: Response might be raw data (Excel/CSV)")

            _LOGGER.error("DEBUG: Final parsed data: %s", parsed_data)
            return parsed_data

        except TokenExpiredError as err:
            _LOGGER.exception("Token expired error: %s", err)
            raise UpdateFailed(f"Token expired: {err}") from err
        except DominionEnergyAPIError as err:
            _LOGGER.exception("API error: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error parsing usage data: %s", err)
            raise UpdateFailed(f"Error parsing data: {err}") from err
