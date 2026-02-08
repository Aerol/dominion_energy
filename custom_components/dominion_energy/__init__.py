"""The Dominion Energy Virginia integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from aiohttp import web
from homeassistant.components.webhook import async_register as webhook_register
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

WEBHOOK_ID = "dominion_energy_token_update"


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
    
    # Register webhook for automatic token updates
    try:
        webhook_register(
            hass,
            DOMAIN,
            "Dominion Energy Token Update",
            WEBHOOK_ID,
            handle_webhook,
        )
        _LOGGER.info("Registered webhook: /api/webhook/%s", WEBHOOK_ID)
    except Exception as err:
        _LOGGER.warning("Failed to register webhook (non-critical): %s", err)
    
    return True


async def handle_webhook(hass: HomeAssistant, webhook_id: str, request):
    """Handle incoming webhook for token updates."""
    try:
        data = await request.json()
        _LOGGER.info("Received token update via webhook")
        
        token = data.get('token')
        account_number = data.get('account_number')
        customer_number = data.get('customer_number')
        meter_number = data.get('meter_number')
        gigya_login_token = data.get('gigya_login_token')
        
        if not token:
            _LOGGER.error("Webhook received without token")
            return web.Response(status=400, text="Missing token")
        
        # Find the Dominion Energy config entry
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            _LOGGER.error("No Dominion Energy integration configured")
            return web.Response(status=404, text="No integration found")
        
        # Update the first entry (or all of them if multiple)
        for entry in entries:
            # Update the config entry data
            new_data = {**entry.data}
            new_data['manual_token'] = token
            if account_number:
                new_data['account_number'] = account_number
            if customer_number:
                new_data['customer_number'] = customer_number
            if meter_number:
                new_data['meter_number'] = meter_number
            if gigya_login_token:
                new_data['gigya_login_token'] = gigya_login_token
                _LOGGER.info("Saved Gigya login token (will enable automatic auth)")
            
            hass.config_entries.async_update_entry(entry, data=new_data)
            
            # Update the API instance with new token
            if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
                api = hass.data[DOMAIN][entry.entry_id].get('api')
                if api:
                    api._bearer_token = token
                    if account_number:
                        api._account_number = account_number
                    if customer_number:
                        api._customer_number = customer_number
                    if meter_number:
                        api._meter_number = meter_number
                    _LOGGER.info("Updated API token for entry %s", entry.entry_id)
                
                # Trigger immediate refresh
                coordinator = hass.data[DOMAIN][entry.entry_id].get('coordinator')
                if coordinator:
                    await coordinator.async_request_refresh()
                    _LOGGER.info("Triggered data refresh after token update")
        
        # Send persistent notification to user
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "message": f"Dominion Energy token updated automatically at {data.get('timestamp', 'unknown time')}",
                "title": "Dominion Energy Token Updated",
                "notification_id": "dominion_energy_token_update"
            }
        )
        
        return web.Response(status=200, text="Token updated successfully")
        
    except Exception as err:
        _LOGGER.exception("Error handling webhook: %s", err)
        return web.Response(status=500, text=f"Error: {err}")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok
