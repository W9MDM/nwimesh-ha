"""Event entity that fires for every channel message (handy for automations)."""
from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MeshConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: MeshConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.runtime_data.mesh:
        async_add_entities([MessageEvent(entry)])


class MessageEvent(EventEntity):
    _attr_has_entity_name = True
    _attr_name = "Message"
    _attr_icon = "mdi:message-flash"
    _attr_event_types = ["text", "reaction"]
    _attr_should_poll = False

    def __init__(self, entry: MeshConfigEntry) -> None:
        self.mesh = entry.runtime_data.mesh
        self._attr_unique_id = f"{entry.entry_id}_message"
        self._attr_device_info = entry.runtime_data.device

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.mesh.async_add_message_listener(self._on_message))

    @callback
    def _on_message(self, msg: dict) -> None:
        self._trigger_event("reaction" if msg.get("reaction") else "text", msg)
        self.async_write_ha_state()
