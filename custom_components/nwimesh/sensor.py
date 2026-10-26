"""NWI Mesh sensors: HopWatch network stats + live channel messages."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MeshConfigEntry, MeshData
from .coordinator import StatsCoordinator


def _pct(part: float | None, whole: float | None) -> float | None:
    if part is None or not whole:
        return None
    return round(part / whole * 100)


@dataclass(frozen=True, kw_only=True)
class StatsDescription(SensorEntityDescription):
    value_fn: Callable[[dict], Any]
    attrs_fn: Callable[[dict], dict] | None = None


M = SensorStateClass.MEASUREMENT

STATS: tuple[StatsDescription, ...] = (
    StatsDescription(
        key="health", name="Health", icon="mdi:heart-pulse", state_class=M,
        value_fn=lambda d: d["health"].get("score"),
        # sub-scores are null while a factor has no evidence yet
        attrs_fn=lambda d: {k: d["health"].get(k) for k in
                            ("label", "utilization", "delivery_ratio", "gateway_coverage", "active_node_trend")},
    ),
    StatsDescription(
        key="anomaly_flags", name="Anomaly flags", icon="mdi:alert-decagram", state_class=M,
        native_unit_of_measurement="flags",
        value_fn=lambda d: d["health"].get("anomalies"),
    ),
    StatsDescription(
        key="active_nodes", name="Active nodes", icon="mdi:radio-tower", state_class=M,
        native_unit_of_measurement="nodes",
        value_fn=lambda d: d["nodes"].get("active_24h"),
        attrs_fn=lambda d: {"active_latest_hour": d["nodes"].get("active_48h")},
    ),
    StatsDescription(
        key="known_nodes", name="Known nodes", icon="mdi:account-group", state_class=M,
        native_unit_of_measurement="nodes", value_fn=lambda d: d["nodes"].get("known"),
    ),
    StatsDescription(
        key="new_nodes_today", name="New nodes today", icon="mdi:new-box", state_class=M,
        native_unit_of_measurement="nodes", value_fn=lambda d: d["nodes"].get("new_24h"),
    ),
    StatsDescription(
        key="new_nodes_this_week", name="New nodes this week", icon="mdi:calendar-plus", state_class=M,
        native_unit_of_measurement="nodes", value_fn=lambda d: d["nodes"].get("new_7d"),
    ),
    StatsDescription(
        key="gateways", name="Gateways", icon="mdi:access-point-network", state_class=M,
        native_unit_of_measurement="gateways", value_fn=lambda d: d["gateways"].get("count"),
        attrs_fn=lambda d: {"direct_pairs": d["gateways"].get("direct_pairs")},
    ),
    StatsDescription(
        key="packets_today", name="Packets today", icon="mdi:swap-vertical-bold", state_class=M,
        native_unit_of_measurement="packets", value_fn=lambda d: d["traffic"].get("packets_24h"),
        attrs_fn=lambda d: {k: d["traffic"].get(k) for k in ("receptions_24h", "direct", "relayed")},
    ),
    StatsDescription(
        key="packet_rate", name="Packet rate", icon="mdi:speedometer", state_class=M,
        native_unit_of_measurement="packets/h", value_fn=lambda d: d["traffic"].get("packets_per_hr_48h"),
    ),
    StatsDescription(
        key="channel_utilization", name="Channel utilization", icon="mdi:sine-wave", state_class=M,
        native_unit_of_measurement=PERCENTAGE, suggested_display_precision=1,
        value_fn=lambda d: d["traffic"].get("channel_util_48h_pct"),
    ),
    StatsDescription(
        key="delivery_ratio", name="Delivery ratio", icon="mdi:check-network", state_class=M,
        native_unit_of_measurement=PERCENTAGE, value_fn=lambda d: d["health"].get("delivery_ratio"),
    ),
    StatsDescription(
        key="relayed_share", name="Relayed share", icon="mdi:transit-connection-variant", state_class=M,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _pct(d["traffic"].get("relayed"),
                                (d["traffic"].get("relayed") or 0) + (d["traffic"].get("direct") or 0)),
    ),
    StatsDescription(
        key="messages_today", name="Messages today", icon="mdi:message-text", state_class=M,
        native_unit_of_measurement="messages", value_fn=lambda d: d["traffic"].get("text_messages_today"),
    ),
    StatsDescription(
        key="encrypted_nodes", name="Encrypted nodes", icon="mdi:shield-key", state_class=M,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _pct(d["nodes"].get("with_public_key"), d["nodes"].get("known")),
    ),
    StatsDescription(
        key="mqtt_brokers_up", name="MQTT brokers up", icon="mdi:server-network", state_class=M,
        native_unit_of_measurement="brokers",
        # skip the RF station row ("node") and disabled placeholders
        value_fn=lambda d: sum(1 for b in d.get("brokers", [])
                               if b.get("up") and b.get("name") not in ("node", "primary")),
        attrs_fn=lambda d: {"brokers": d.get("brokers", []), "generated_at": d.get("generated_at")},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: MeshConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = entry.runtime_data
    entities: list[SensorEntity] = []
    if data.stats:
        entities += [StatsSensor(data, entry.entry_id, desc) for desc in STATS]
    if data.mesh:
        entities += [
            LastMessageSensor(data, entry.entry_id),
            MeshCounter(data, entry.entry_id, "messages_heard", "Messages heard", "mdi:message-badge",
                        "messages", lambda m: m.messages_heard),
            MeshCounter(data, entry.entry_id, "nodes_heard", "Nodes named", "mdi:card-account-details",
                        "nodes", lambda m: len(m.nodes)),
        ]
    async_add_entities(entities)


class StatsSensor(CoordinatorEntity[StatsCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: StatsDescription

    def __init__(self, data: MeshData, entry_id: str, desc: StatsDescription) -> None:
        super().__init__(data.stats)
        self.entity_description = desc
        self._attr_unique_id = f"{entry_id}_{desc.key}"
        self._attr_device_info = data.device

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def native_value(self):
        try:
            return self.entity_description.value_fn(self.coordinator.data)
        except (KeyError, TypeError, AttributeError):
            return None

    @property
    def extra_state_attributes(self):
        if not self.entity_description.attrs_fn or not self.coordinator.data:
            return None
        try:
            return self.entity_description.attrs_fn(self.coordinator.data)
        except (KeyError, TypeError, AttributeError):
            return None


class _MeshEntity(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, data: MeshData, entry_id: str, key: str) -> None:
        self.mesh = data.mesh
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = data.device

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.mesh.async_add_listener(self.async_write_ha_state))


class LastMessageSensor(_MeshEntity):
    """State = latest channel message; attribute `recent` = rolling log."""

    _attr_name = "Last message"
    _attr_icon = "mdi:message-text-outline"
    # the log is UI data, not worth writing to the recorder every message
    _unrecorded_attributes = frozenset({"recent"})

    def __init__(self, data: MeshData, entry_id: str) -> None:
        super().__init__(data, entry_id, "last_message")

    @property
    def native_value(self):
        if not self.mesh.messages:
            return None
        return self.mesh.messages[0]["text"][:255]

    @property
    def extra_state_attributes(self):
        latest = self.mesh.messages[0] if self.mesh.messages else {}
        return {
            **{k: v for k, v in latest.items() if k != "text"},
            "recent": list(self.mesh.messages),
        }


class MeshCounter(_MeshEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, data, entry_id, key, name, icon, unit, fn) -> None:
        super().__init__(data, entry_id, key)
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._fn = fn

    @property
    def native_value(self):
        return self._fn(self.mesh)
