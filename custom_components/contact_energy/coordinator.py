"""DataUpdateCoordinator for Contact Energy."""

import logging
from datetime import datetime, timedelta

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
    StatisticMeanType,
)
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ContactEnergyApi
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ContactEnergyCoordinator(DataUpdateCoordinator):
    """Fetch Contact Energy usage data and push to HA statistics."""

    def __init__(self, hass: HomeAssistant, api: ContactEnergyApi, usage_days: int):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=3),
        )
        self._api = api
        self._usage_days = usage_days

    async def _async_update_data(self) -> dict:
        _LOGGER.debug("Beginning usage update")

        if not self._api._api_token:
            _LOGGER.info("Not logged in, logging in now...")
            result = await self.hass.async_add_executor_job(self._api.login)
            if not result:
                raise UpdateFailed("Login failed — check credentials")

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        kwh_statistics = []
        kwh_running_sum = 0.0
        free_kwh_statistics = []
        free_kwh_running_sum = 0.0

        for i in range(self._usage_days):
            previous_day = today - timedelta(days=self._usage_days - i)
            target_date = previous_day.isoformat()[:10]
            _LOGGER.debug("Fetching usage data for %s", target_date)
            response = await self.hass.async_add_executor_job(self._api.get_usage, target_date)
            if response and response[0]:
                for point in response:
                    if point["value"]:
                        kwh_running_sum += float(point["value"])
                        free_kwh_running_sum += float(point["unchargedValue"])
                        start = datetime.strptime(point["date"], "%Y-%m-%dT%H:%M:%S.%f%z")
                        kwh_statistics.append(StatisticData(start=start, sum=kwh_running_sum))
                        free_kwh_statistics.append(StatisticData(start=start, sum=free_kwh_running_sum))

        _LOGGER.info(
            "Fetched usage data: %.2f kWh (%d datapoints)",
            kwh_running_sum,
            len(kwh_statistics),
        )

        async_add_external_statistics(
            self.hass,
            StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name="ContactEnergy",
                source=DOMAIN,
                statistic_id=f"{DOMAIN}:energy_consumption",
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                unit_class="energy",
            ),
            kwh_statistics,
        )

        async_add_external_statistics(
            self.hass,
            StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name="FreeContactEnergy",
                source=DOMAIN,
                statistic_id=f"{DOMAIN}:free_energy_consumption",
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                unit_class="energy",
            ),
            free_kwh_statistics,
        )

        return {"kwh_total": kwh_running_sum, "free_kwh_total": free_kwh_running_sum}