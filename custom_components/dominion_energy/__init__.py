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
        
        _LOGGER.error("DEBUG: Config entry data keys: %s", list(entry.data.keys()))
        _LOGGER.error("DEBUG: Account number from config: %s", api._account_number)
        _LOGGER.error("DEBUG: Customer number from config: %s", api._customer_number)
        _LOGGER.error("DEBUG: Meter number from config: %s", api._meter_number)
        
        if not api._account_number or not api._meter_number:
            _LOGGER.error("Missing account/meter numbers in config entry! Please reconfigure integration.")
            return False

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

    def _parse_excel_data(self, excel_bytes: bytes) -> dict:
        """Parse Excel data and return totals."""
        try:
            from openpyxl import load_workbook
            from io import BytesIO
            
            wb = load_workbook(BytesIO(excel_bytes))
            ws = wb.active
            
            total_usage = 0
            last_value = 0
            last_time = None
            reading_count = 0
            
            for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                if not row or len(row) < 4:
                    continue
                
                date_str = row[2]
                
                for col_idx in range(3, min(len(row), 51)):
                    value = row[col_idx]
                    if value is not None and value != '':
                        try:
                            usage = float(value)
                            total_usage += usage
                            last_value = usage
                            last_time = f"{date_str} {ws.cell(1, col_idx + 1).value}"
                            reading_count += 1
                        except (ValueError, TypeError):
                            pass
            
            return {
                "total": total_usage,
                "last_value": last_value,
                "last_time": last_time,
                "count": reading_count
            }
        except Exception as e:
            _LOGGER.error("Error parsing Excel data: %s", e, exc_info=True)
            return {"total": 0, "last_value": 0, "last_time": None, "count": 0}

    def _parse_green_button_data(self, xml_bytes: bytes) -> float:
        """Parse Green Button XML and return total kWh."""
        try:
            import xml.etree.ElementTree as ET
            
            root = ET.fromstring(xml_bytes)
            
            ET.register_namespace('espi', 'http://naesb.org/espi')
            ns = {'espi': 'http://naesb.org/espi'}
            
            # Get powerOfTenMultiplier
            power_multiplier = 0
            reading_type = root.find('.//espi:ReadingType', ns)
            if reading_type is not None:
                power_elem = reading_type.find('espi:powerOfTenMultiplier', ns)
                if power_elem is not None and power_elem.text:
                    power_multiplier = int(power_elem.text)
            
            # Find all IntervalReading elements
            readings = root.findall('.//espi:IntervalReading', ns)
            
            total = 0
            for reading in readings:
                value_elem = reading.find('espi:value', ns)
                if value_elem is not None and value_elem.text:
                    try:
                        raw_value = int(value_elem.text)
                        wh = raw_value * (10 ** power_multiplier)
                        kwh = wh / 1000.0
                        total += kwh
                    except (ValueError, TypeError):
                        pass
            
            return total
        except Exception as e:
            _LOGGER.error("Error parsing Green Button XML: %s", e, exc_info=True)
            return 0

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            # Ensure token is valid (auto-refresh if needed)
            if self.api.has_tokens:
                await self.api.async_ensure_valid_token()

            # Fetch BOTH Excel and Green Button data for comparison
            _LOGGER.error("DEBUG: Fetching usage data with account=%s, meter=%s", 
                         self.api._account_number, self.api._meter_number)
            
            from datetime import datetime, timedelta
            
            # Define date ranges
            today = datetime.now().date()
            yesterday = today - timedelta(days=1)
            first_of_month = today.replace(day=1)
            
            # Fetch YESTERDAY's data for daily usage (today's data isn't finalized yet)
            _LOGGER.error("DEBUG: === Fetching YESTERDAY's data (%s) for daily usage ===", yesterday)
            daily_excel = await self.api.async_get_usage(
                start_date=datetime.combine(yesterday, datetime.min.time()),
                end_date=datetime.combine(yesterday, datetime.max.time())
            )
            
            try:
                daily_green_button = await self.api.async_get_green_button_data(
                    start_date=datetime.combine(yesterday, datetime.min.time()),
                    end_date=datetime.combine(yesterday, datetime.max.time())
                )
            except Exception as e:
                _LOGGER.error("DEBUG: Failed to fetch daily Green Button data: %s", e)
                daily_green_button = None
            
            # Fetch MONTH's data for monthly usage
            _LOGGER.error("DEBUG: === Fetching MONTHLY data (%s to %s) ===", first_of_month, today)
            monthly_excel = await self.api.async_get_usage(
                start_date=datetime.combine(first_of_month, datetime.min.time()),
                end_date=datetime.combine(today, datetime.max.time())
            )
            
            try:
                monthly_green_button = await self.api.async_get_green_button_data(
                    start_date=datetime.combine(first_of_month, datetime.min.time()),
                    end_date=datetime.combine(today, datetime.max.time())
                )
            except Exception as e:
                _LOGGER.error("DEBUG: Failed to fetch monthly Green Button data: %s", e)
                monthly_green_button = None

            # Parse the response into sensor data
            parsed_data = {
                "account_number": self.api._account_number,
                "meter_number": self.api._meter_number,
                "last_hour_usage": 0,
                "last_hour_reading_time": None,
                "daily_usage": 0,
                "monthly_usage": 0,
                "estimated_cost": 0,
                "daily_excel": 0,
                "daily_green_button": 0,
                "monthly_excel": 0,
                "monthly_green_button": 0,
            }
            
            # Parse DAILY data
            daily_excel_total = 0
            daily_gb_total = 0
            last_value = 0
            last_time = None
            
            if daily_excel and isinstance(daily_excel, dict) and "raw_excel" in daily_excel:
                _LOGGER.error("DEBUG: === Processing DAILY Excel ===")
                excel_result = self._parse_excel_data(daily_excel["raw_excel"])
                daily_excel_total = excel_result["total"]
                last_value = excel_result["last_value"]
                last_time = excel_result["last_time"]
                _LOGGER.error("DEBUG: Daily Excel: %.2f kWh", daily_excel_total)
            
            if daily_green_button and isinstance(daily_green_button, dict) and "raw_xml" in daily_green_button:
                _LOGGER.error("DEBUG: === Processing DAILY Green Button ===")
                daily_gb_total = self._parse_green_button_data(daily_green_button["raw_xml"])
                _LOGGER.error("DEBUG: Daily Green Button: %.2f kWh", daily_gb_total)
            
            # Use Green Button for daily if available, otherwise Excel
            parsed_data["daily_usage"] = daily_gb_total if daily_gb_total > 0 else daily_excel_total
            parsed_data["daily_excel"] = daily_excel_total
            parsed_data["daily_green_button"] = daily_gb_total
            parsed_data["last_hour_usage"] = last_value
            parsed_data["last_hour_reading_time"] = last_time
            
            # Parse MONTHLY data
            monthly_excel_total = 0
            monthly_gb_total = 0
            
            if monthly_excel and isinstance(monthly_excel, dict) and "raw_excel" in monthly_excel:
                _LOGGER.error("DEBUG: === Processing MONTHLY Excel ===")
                excel_result = self._parse_excel_data(monthly_excel["raw_excel"])
                monthly_excel_total = excel_result["total"]
                _LOGGER.error("DEBUG: Monthly Excel: %.2f kWh", monthly_excel_total)
            
            if monthly_green_button and isinstance(monthly_green_button, dict) and "raw_xml" in monthly_green_button:
                _LOGGER.error("DEBUG: === Processing MONTHLY Green Button ===")
                monthly_gb_total = self._parse_green_button_data(monthly_green_button["raw_xml"])
                _LOGGER.error("DEBUG: Monthly Green Button: %.2f kWh", monthly_gb_total)
            
            # Use Green Button for monthly if available, otherwise Excel
            parsed_data["monthly_usage"] = monthly_gb_total if monthly_gb_total > 0 else monthly_excel_total
            parsed_data["monthly_excel"] = monthly_excel_total
            parsed_data["monthly_green_button"] = monthly_gb_total
            
            # Estimate cost based on monthly usage
            parsed_data["estimated_cost"] = round(parsed_data["monthly_usage"] * 0.12, 2)
            
            # Log comparison
            _LOGGER.error("DEBUG: === FINAL RESULTS ===")
            _LOGGER.error("DEBUG: Daily:   %.2f kWh (Excel: %.2f, GB: %.2f)", 
                         parsed_data["daily_usage"], daily_excel_total, daily_gb_total)
            _LOGGER.error("DEBUG: Monthly: %.2f kWh (Excel: %.2f, GB: %.2f)", 
                         parsed_data["monthly_usage"], monthly_excel_total, monthly_gb_total)

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
