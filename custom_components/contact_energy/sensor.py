"""Contact Energy sensors."""

import logging
import voluptuous as vol
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, UnitOfEnergy
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ContactEnergyApi
from .const import DOMAIN, SENSOR_USAGE_NAME, CONF_USAGE_DAYS
from .coordinator import ContactEnergyCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_EMAIL): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_USAGE_DAYS, default=10): cv.positive_int,
    }
)

SCAN_INTERVAL = timedelta(hours=3)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Contact Energy sensors from a config entry."""
    coordinator: ContactEnergyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ContactEnergyUsageSensor(coordinator)])


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the platform from YAML (legacy)."""
    api = ContactEnergyApi(config[CONF_EMAIL], config[CONF_PASSWORD])
    usage_days = config.get(CONF_USAGE_DAYS, 10)
    coordinator = ContactEnergyCoordinator(hass, api, usage_days)
    await coordinator.async_config_entry_first_refresh()
    async_add_entities([ContactEnergyUsageSensor(coordinator)])


class ContactEnergyUsageSensor(CoordinatorEntity, SensorEntity):
    """Contact Energy usage sensor backed by a DataUpdateCoordinator."""

    _attr_icon = "mdi:meter-electric"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = "energy"
    _attr_state_class = "total"
    _attr_unique_id = DOMAIN

    def __init__(self, coordinator: ContactEnergyCoordinator):
        super().__init__(coordinator)
        self._attr_name = SENSOR_USAGE_NAME

    @property
    def native_value(self):
        """Return latest total kWh."""
        if self.coordinator.data:
            return self.coordinator.data.get("kwh_total")
        return None