"""NWI Mesh connectivity sensors."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MeshConfigEntry, MeshData
from .coordinator import StatsCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: MeshConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    if data.stats:
        entities += [ApiOnline(data, entry.entry_id), BrokerUp(data, entry.entry_id)]
    if data.mesh:
        entities.append(MqttConnected(data, entry.entry_id))
    async_add_entities(entities)


class _Base(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def _setup(self, data: MeshData, entry_id: str, key: str, name: str, icon: str) -> None:
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_device_info = data.device


class ApiOnline(CoordinatorEntity[StatsCoordinator], _Base):
    def __init__(self, data: MeshData, entry_id: str) -> None:
        super().__init__(data.stats)
        self._setup(data, entry_id, "online", "Online", "mdi:api")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


class BrokerUp(CoordinatorEntity[StatsCoordinator], _Base):
    """The mesh's own MQTT broker, as reported by HopWatch."""

    def __init__(self, data: MeshData, entry_id: str) -> None:
        super().__init__(data.stats)
        self._broker = data.broker_name
        self._setup(data, entry_id, "broker", "Broker", "mdi:server-network")

    @property
    def is_on(self) -> bool | None:
        for b in (self.coordinator.data or {}).get("brokers", []):
            if b.get("name") == self._broker:
                return bool(b.get("up"))
        return None


class MqttConnected(_Base):
    _attr_should_poll = False

    def __init__(self, data: MeshData, entry_id: str) -> None:
        self.mesh = data.mesh
        self._setup(data, entry_id, "mqtt_connected", "MQTT connected", "mdi:lan-connect")

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.mesh.async_add_listener(self.async_write_ha_state))

    @property
    def is_on(self) -> bool:
        return self.mesh.connected
