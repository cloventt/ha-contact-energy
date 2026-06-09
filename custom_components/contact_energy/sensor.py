"""Contact Energy sensors."""

from datetime import datetime, timedelta

import logging
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, UnitOfEnergy
from homeassistant.components.sensor import SensorEntity

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData, StatisticMeanType
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
)

from .api import ContactEnergyApi

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SENSOR_USAGE_NAME,
    CONF_USAGE_DAYS,
)

NAME = DOMAIN
ISSUEURL = "https://github.com/cloventt/hacs_contact_energy/issues"

STARTUP = f"""
-------------------------------------------------------------------
{NAME}
This is a custom component
If you have any issues with this you need to open an issue here:
{ISSUEURL}
-------------------------------------------------------------------
"""

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
    data = hass.data[DOMAIN][entry.entry_id]
    email = data[CONF_EMAIL]
    password = data[CONF_PASSWORD]
    usage_days = data.get(CONF_USAGE_DAYS, 10)

    api = ContactEnergyApi(email, password)
    sensors = [ContactEnergyUsageSensor(SENSOR_USAGE_NAME, api, usage_days)]
    async_add_entities(sensors, True)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the platform async."""
    email = config.get(CONF_EMAIL)
    password = config.get(CONF_PASSWORD)

    usage_days = config.get(CONF_USAGE_DAYS)

    api = ContactEnergyApi(email, password)

    _LOGGER.debug("Setting up sensor(s)...")

    sensors = [ContactEnergyUsageSensor(SENSOR_USAGE_NAME, api, usage_days)]
    async_add_entities(sensors, True)


class ContactEnergyUsageSensor(SensorEntity):
    """Define Contact Energy Usage sensor."""

    def __init__(self, name, api, usage_days):
        """Intialise the sensor."""
        self._name = name
        self._icon = "mdi:meter-electric"
        self._state = 0
        self._unit_of_measurement = "kWh"
        self._unique_id = DOMAIN
        self._device_class = "energy"
        self._state_class = "total"
        self._state_attributes = {}
        self._usage_days = usage_days
        self._api = api

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the sensor."""
        return self._state_attributes

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def state_class(self):
        """Return the state class."""
        return self._state_class

    @property
    def device_class(self):
        """Return the device class."""
        return self._device_class

    @property
    def unique_id(self):
        """Return the unique id."""
        return self._unique_id

    async def async_update(self):
        """Begin usage update."""
        _LOGGER.debug("Beginning usage update")

        if self._api._api_token:
            _LOGGER.debug("We appear to be logged in (lets not verify it for now)")
        else:
            _LOGGER.info("Haven't logged in yet, lets login now...")
            result = await self.hass.async_add_executor_job(self._api.login)
            if result is False:
                _LOGGER.error(
                    "Failed to get past login (usage will not be updated) - check the username and password are valid"
                )
                return

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        _LOGGER.debug("Fetching usage data")

        kWhStatistics = []
        kWhRunningSum = 0.0

        freeKWhStatistics = []
        freeKWhRunningSum = 0.0

        for i in range(self._usage_days):
            previous_day = today - timedelta(days=self._usage_days - i)
            target_date = previous_day.isoformat()[:10]
            _LOGGER.debug("Fetching usage data for %s", target_date)
            response = await self.hass.async_add_executor_job(self._api.get_usage, target_date)
            if response and response[0]:
                for point in response:
                    if point["value"]:
                        kWhRunningSum = kWhRunningSum + float(point["value"])
                        freeKWhRunningSum = freeKWhRunningSum + float(point["unchargedValue"])

                        freeKWhStatistics.append(
                            StatisticData(
                                start=datetime.strptime(
                                    point["date"], "%Y-%m-%dT%H:%M:%S.%f%z"
                                ),
                                sum=freeKWhRunningSum,
                            )
                        )
                        kWhStatistics.append(
                            StatisticData(
                                start=datetime.strptime(
                                    point["date"], "%Y-%m-%dT%H:%M:%S.%f%z"
                                ),
                                sum=kWhRunningSum,
                            )
                        )
            _LOGGER.debug("Finished fetching usage data for %s", target_date)

        _LOGGER.info("Finished fetching usage data, total of %.2f kWh recorded (%d datapoints)", kWhRunningSum, len(kWhStatistics))
        kWhMetadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name="ContactEnergy",
            source=DOMAIN,
            statistic_id=f"{DOMAIN}:energy_consumption",
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            unit_class="energy",
        )
        async_add_external_statistics(self.hass, kWhMetadata, kWhStatistics)

        freeKWHMetadata = StatisticMetaData(
            has_sum=True,
            name="FreeContactEnergy",
            source=DOMAIN,
            statistic_id=f"{DOMAIN}:free_energy_consumption",
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            mean_type=StatisticMeanType.NONE,
            unit_class="energy",
        )
        async_add_external_statistics(self.hass, freeKWHMetadata, freeKWhStatistics)
        _LOGGER.debug("Finished usage update")
