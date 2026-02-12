"""Sensor platform for Dominion Energy Virginia integration."""
from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower, CURRENCY_DOLLAR
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dominion Energy sensors from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    sensors = [
        DominionEnergyCurrentHourUsageSensor(coordinator, config_entry),
        DominionEnergyDailyUsageSensor(coordinator, config_entry),
        DominionEnergyMonthlyUsageSensor(coordinator, config_entry),
        DominionEnergyBillingUsageSensor(coordinator, config_entry),
        DominionEnergyEstimatedCostSensor(coordinator, config_entry),
        DominionEnergyAccountNumberSensor(coordinator, config_entry),
        DominionEnergyMeterNumberSensor(coordinator, config_entry),
    ]
    
    async_add_entities(sensors)


class DominionEnergySensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Dominion Energy sensors."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_has_entity_name = True

    @property
    def device_info(self):
        """Return device information about this sensor."""
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": "Dominion Energy Account",
            "manufacturer": "Dominion Energy",
            "model": "Energy Monitor",
        }


class DominionEnergyCurrentHourUsageSensor(DominionEnergySensorBase):
    """Sensor for most recent hourly energy usage."""

    _attr_name = "Last Hour Usage"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:clock-outline"

    @property
    def unique_id(self) -> str:
        """Return unique ID for this sensor."""
        return f"{self._config_entry.entry_id}_hourly_usage_v2"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            value = self.coordinator.data.get("last_hour_usage", 0)
            _LOGGER.debug("Last hour usage sensor value: %s", value)
            return value
        return None

    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        if self.coordinator.data:
            return {
                "last_reading_time": self.coordinator.data.get("last_hour_reading_time"),
            }
        return None


class DominionEnergyDailyUsageSensor(DominionEnergySensorBase):
    """Sensor for daily energy usage (yesterday's complete data)."""

    _attr_name = "Yesterday Usage"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    @property
    def unique_id(self) -> str:
        """Return unique ID for this sensor."""
        return f"{self._config_entry.entry_id}_daily_usage"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("daily_usage")
        return None


class DominionEnergyMonthlyUsageSensor(DominionEnergySensorBase):
    """Sensor for monthly energy usage (calendar month)."""

    _attr_name = "Monthly Usage"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    @property
    def unique_id(self) -> str:
        """Return unique ID for this sensor."""
        return f"{self._config_entry.entry_id}_monthly_usage"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("monthly_usage")
        return None


class DominionEnergyBillingUsageSensor(DominionEnergySensorBase):
    """Sensor for billing period energy usage (matches Dominion billing cycle)."""

    _attr_name = "Billing Period Usage"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:file-document-outline"

    @property
    def unique_id(self) -> str:
        """Return unique ID for this sensor."""
        return f"{self._config_entry.entry_id}_billing_usage"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("billing_usage")
        return None


class DominionEnergyEstimatedCostSensor(DominionEnergySensorBase):
    """Sensor for estimated energy cost."""

    _attr_name = "Estimated Cost"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = CURRENCY_DOLLAR

    @property
    def unique_id(self) -> str:
        """Return unique ID for this sensor."""
        return f"{self._config_entry.entry_id}_estimated_cost"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("estimated_cost")
        return None


class DominionEnergyAccountNumberSensor(DominionEnergySensorBase):
    """Sensor for account number."""

    _attr_name = "Account Number"
    _attr_icon = "mdi:account"

    @property
    def unique_id(self) -> str:
        """Return unique ID for this sensor."""
        return f"{self._config_entry.entry_id}_account_number"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("account_number")
        return None


class DominionEnergyMeterNumberSensor(DominionEnergySensorBase):
    """Sensor for meter number."""

    _attr_name = "Meter Number"
    _attr_icon = "mdi:counter"

    @property
    def unique_id(self) -> str:
        """Return unique ID for this sensor."""
        return f"{self._config_entry.entry_id}_meter_number"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("meter_number")
        return None
