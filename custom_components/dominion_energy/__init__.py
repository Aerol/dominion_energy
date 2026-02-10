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

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            # Ensure token is valid (auto-refresh if needed)
            if self.api.has_tokens:
                await self.api.async_ensure_valid_token()

            # Fetch BOTH Excel and Green Button data for comparison
            _LOGGER.error("DEBUG: Fetching usage data with account=%s, meter=%s", 
                         self.api._account_number, self.api._meter_number)
            
            # Fetch Excel data
            _LOGGER.error("DEBUG: === Fetching Excel data ===")
            excel_data = await self.api.async_get_usage()
            
            # Fetch Green Button data
            _LOGGER.error("DEBUG: === Fetching Green Button data ===")
            try:
                green_button_data = await self.api.async_get_green_button_data()
            except Exception as e:
                _LOGGER.error("DEBUG: Failed to fetch Green Button data: %s", e)
                green_button_data = None
            
            _LOGGER.error("DEBUG: Excel data keys: %s", list(excel_data.keys()) if isinstance(excel_data, dict) else type(excel_data))
            if green_button_data:
                _LOGGER.error("DEBUG: Green Button data keys: %s", list(green_button_data.keys()) if isinstance(green_button_data, dict) else type(green_button_data))

            # Parse the response into sensor data
            parsed_data = {
                "account_number": self.api._account_number,
                "meter_number": self.api._meter_number,
                "last_hour_usage": 0,
                "last_hour_reading_time": None,
                "daily_usage": 0,
                "monthly_usage": 0,
                "estimated_cost": 0,
                "excel_total": 0,
                "green_button_total": 0,
            }
            
            excel_total = 0
            green_button_total = 0
            
            # Parse Excel data
            if excel_data and isinstance(excel_data, dict) and "raw_excel" in excel_data:
                _LOGGER.error("DEBUG: === Processing Excel response ===")
                
                try:
                    from openpyxl import load_workbook
                    from io import BytesIO
                    
                    excel_bytes = excel_data["raw_excel"]
                    _LOGGER.error("DEBUG: Excel data size: %d bytes", len(excel_bytes))
                    
                    wb = load_workbook(BytesIO(excel_bytes))
                    ws = wb.active
                    
                    _LOGGER.error("DEBUG: Excel loaded, %d rows", ws.max_row)
                    
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
                                    excel_total += usage
                                    last_value = usage
                                    last_time = f"{date_str} {ws.cell(1, col_idx + 1).value}"
                                    reading_count += 1
                                except (ValueError, TypeError):
                                    pass
                    
                    parsed_data["last_hour_usage"] = last_value
                    parsed_data["last_hour_reading_time"] = last_time
                    parsed_data["excel_total"] = excel_total
                    
                    _LOGGER.error("DEBUG: Excel parsed: %d readings, total: %.2f kWh", 
                               reading_count, excel_total)
                    
                except Exception as e:
                    _LOGGER.error("Error parsing Excel data: %s", e, exc_info=True)
            
            # Parse Green Button XML
            if green_button_data and isinstance(green_button_data, dict) and "raw_xml" in green_button_data:
                _LOGGER.error("DEBUG: === Processing Green Button XML ===")
                
                try:
                    import xml.etree.ElementTree as ET
                    
                    xml_bytes = green_button_data["raw_xml"]
                    _LOGGER.error("DEBUG: Green Button XML size: %d bytes", len(xml_bytes))
                    
                    # Parse XML
                    root = ET.fromstring(xml_bytes)
                    
                    # Green Button XML uses ESPI namespace
                    ns = {'espi': 'http://naesb.org/espi'}
                    
                    # Find all IntervalReading elements
                    readings = root.findall('.//espi:IntervalReading', ns)
                    _LOGGER.error("DEBUG: Found %d IntervalReading elements", len(readings))
                    
                    if not readings:
                        # Try without namespace
                        readings = root.findall('.//IntervalReading')
                        _LOGGER.error("DEBUG: Without namespace found %d IntervalReading elements", len(readings))
                    
                    for reading in readings:
                        # Get value in Wh
                        value_elem = reading.find('.//espi:value', ns) or reading.find('.//value')
                        if value_elem is not None and value_elem.text:
                            try:
                                # Green Button values are typically in Wh, convert to kWh
                                wh = float(value_elem.text)
                                kwh = wh / 1000.0
                                green_button_total += kwh
                            except (ValueError, TypeError):
                                pass
                    
                    parsed_data["green_button_total"] = green_button_total
                    
                    _LOGGER.error("DEBUG: Green Button parsed: %d readings, total: %.2f kWh", 
                               len(readings), green_button_total)
                    
                except Exception as e:
                    _LOGGER.error("Error parsing Green Button XML: %s", e, exc_info=True)
            
            # Use Green Button as primary if available, otherwise Excel
            if green_button_total > 0:
                _LOGGER.info("Using Green Button data (more accurate)")
                parsed_data["daily_usage"] = green_button_total
                parsed_data["monthly_usage"] = green_button_total
            elif excel_total > 0:
                _LOGGER.info("Using Excel data (Green Button unavailable)")
                parsed_data["daily_usage"] = excel_total
                parsed_data["monthly_usage"] = excel_total
            
            parsed_data["estimated_cost"] = round(parsed_data["daily_usage"] * 0.12, 2)
            
            # Log comparison
            if excel_total > 0 and green_button_total > 0:
                diff = abs(excel_total - green_button_total)
                diff_pct = (diff / excel_total) * 100 if excel_total > 0 else 0
                _LOGGER.error("DEBUG: === COMPARISON ===")
                _LOGGER.error("DEBUG: Excel total:        %.2f kWh", excel_total)
                _LOGGER.error("DEBUG: Green Button total: %.2f kWh", green_button_total)
                _LOGGER.error("DEBUG: Difference:         %.2f kWh (%.1f%%)", diff, diff_pct)

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
