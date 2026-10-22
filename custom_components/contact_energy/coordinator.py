"""DataUpdateCoordinator for Contact Energy."""

import logging
from datetime import datetime, timedelta

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
    StatisticMeanType,
)
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ContactEnergyApi
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

KWH_STATISTIC_ID = f"{DOMAIN}:energy_consumption"
FREE_KWH_STATISTIC_ID = f"{DOMAIN}:free_energy_consumption"


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

    async def _async_last_stat(self, statistic_id: str) -> tuple[float, float]:
        """Return (start timestamp, cumulative sum) of the last recorded statistic, so new data continues from it."""
        last_stats = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics, self.hass, 1, statistic_id, True, {"sum"}
        )
        stats = last_stats.get(statistic_id)
        if stats:
            return stats[0]["start"], stats[0]["sum"] or 0.0
        return 0.0, 0.0

    async def _async_update_data(self) -> dict:
        _LOGGER.debug("Beginning usage update")

        # The Contact Energy session token is short-lived, so log in fresh every
        # update rather than only once — otherwise every call 401s after the
        # token expires and we silently stop getting data.
        _LOGGER.debug("Logging in...")
        result = await self.hass.async_add_executor_job(self._api.login)
        if not result:
            raise UpdateFailed("Login failed — check credentials")

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        kwh_statistics = []
        last_start, kwh_running_sum = await self._async_last_stat(KWH_STATISTIC_ID)
        free_kwh_statistics = []
        _, free_kwh_running_sum = await self._async_last_stat(FREE_KWH_STATISTIC_ID)

        for i in range(self._usage_days):
            previous_day = today - timedelta(days=self._usage_days - i)
            target_date = previous_day.isoformat()[:10]
            _LOGGER.debug("Fetching usage data for %s", target_date)
            response = await self.hass.async_add_executor_job(self._api.get_usage, target_date)
            if not response:
                _LOGGER.warning("No usage data returned for %s", target_date)
                continue
            for point in response:
                start = datetime.strptime(point["date"], "%Y-%m-%dT%H:%M:%S.%f%z")
                # The window overlaps previous updates; only add hours we haven't
                # recorded yet, otherwise the cumulative sum double-counts them.
                if point["value"] and start.timestamp() > last_start:
                    kwh_running_sum += float(point["value"])
                    free_kwh_running_sum += float(point["unchargedValue"])
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