"""NWI Mesh: Meshtastic community mesh stats and messages for Home Assistant."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import (
    CONF_BROKER_NAME,
    CONF_CHANNELS,
    CONF_HISTORY,
    CONF_HOPWATCH_URL,
    CONF_ROOT_TOPIC,
    CONF_TLS,
    DEFAULT_BROKER_NAME,
    DEFAULT_HISTORY,
    DOMAIN,
)
from .coordinator import StatsCoordinator
from .mesh import MeshListener

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.EVENT]


@dataclass
class MeshData:
    stats: StatsCoordinator | None
    mesh: MeshListener | None
    device: DeviceInfo
    broker_name: str


type MeshConfigEntry = ConfigEntry[MeshData]


def entry_config(entry: ConfigEntry) -> dict:
    return {**entry.data, **entry.options}


async def async_setup_entry(hass: HomeAssistant, entry: MeshConfigEntry) -> bool:
    conf = entry_config(entry)

    stats = None
    if url := conf.get(CONF_HOPWATCH_URL):
        stats = StatsCoordinator(hass, url)
        await stats.async_config_entry_first_refresh()

    mesh = None
    if conf.get(CONF_HOST):
        mesh = MeshListener(
            hass,
            entry.entry_id,
            conf[CONF_HOST],
            conf[CONF_PORT],
            conf.get(CONF_USERNAME, ""),
            conf.get(CONF_PASSWORD, ""),
            conf[CONF_ROOT_TOPIC],
            conf[CONF_CHANNELS],
            conf.get(CONF_TLS, False),
            int(conf.get(CONF_HISTORY, DEFAULT_HISTORY)),
        )
        await mesh.async_start()

    entry.runtime_data = MeshData(
        stats=stats,
        mesh=mesh,
        device=DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="NWI Mesh Net",
            model="Meshtastic community mesh",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=conf.get(CONF_HOPWATCH_URL) or "https://nwimesh.net",
        ),
        broker_name=conf.get(CONF_BROKER_NAME, DEFAULT_BROKER_NAME),
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MeshConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok and entry.runtime_data.mesh:
        await entry.runtime_data.mesh.async_stop()
    return ok


async def _async_reload(hass: HomeAssistant, entry: MeshConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
