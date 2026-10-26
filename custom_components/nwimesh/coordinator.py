"""HopWatch stats polling."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, STATS_INTERVAL, STATS_PATH

_LOGGER = logging.getLogger(__name__)


async def fetch_stats(hass: HomeAssistant, base_url: str) -> dict:
    session = async_get_clientsession(hass)
    url = base_url.rstrip("/") + STATS_PATH
    async with asyncio.timeout(20):
        resp = await session.get(
            url, headers={"User-Agent": "HomeAssistant-NWIMesh/1.0", "Accept": "application/json"}
        )
        resp.raise_for_status()
        data = await resp.json()
    if not isinstance(data, dict) or "health" not in data:
        raise ValueError("not a HopWatch stats response")
    return data


class StatsCoordinator(DataUpdateCoordinator[dict]):
    """Polls the public HopWatch /api/v1/stats endpoint."""

    def __init__(self, hass: HomeAssistant, base_url: str) -> None:
        super().__init__(
            hass, _LOGGER, name=f"{DOMAIN} stats", update_interval=timedelta(seconds=STATS_INTERVAL)
        )
        self.base_url = base_url

    async def _async_update_data(self) -> dict:
        try:
            return await fetch_stats(self.hass, self.base_url)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise UpdateFailed(f"HopWatch unavailable: {err}") from err
