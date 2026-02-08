"""The Dominion Energy Virginia integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .api import DominionEnergyAPI

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

UPDATE_INTERVAL = timedelta(minutes=30)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dominion Energy Virginia from a config entry."""
    
    auth_method = entry.data.get("auth_method", "automatic")
    _LOGGER.info("Setting up Dominion Energy integration with auth_method: %s", auth_method)
    
    api = DominionEnergyAPI(
        username=entry.data.get("username", ""),
        password=entry.data.get("password", ""),
        session=async_get_clientsession(hass)
    )
    
    # If using manual token, set it directly
    if auth_method == "manual_token":
        token = entry.data.get("manual_token", "")
        account = entry.data.get("account_number", "")
        customer = entry.data.get("customer_number", "")
        meter = entry.data.get("meter_number", "")
        
        _LOGGER.debug("Manual token config - Token length: %d, Account: %s, Customer: %s, Meter: %s", 
                     len(token), account, customer, meter)
        
        api._bearer_token = token
        api._account_number = account
        api._customer_number = customer
        api._meter_number = meter
        
        _LOGGER.info("Using manual token authentication for account %s (token set: %s)", 
                    api._account_number, bool(api._bearer_token))
    else:
        _LOGGER.info("Using automatic authentication")
    
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=api.async_get_usage_data,
        update_interval=UPDATE_INTERVAL,
    )
    
    # Fetch initial data
    _LOGGER.debug("Performing initial data refresh...")
    await coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("Initial refresh complete")
    
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
