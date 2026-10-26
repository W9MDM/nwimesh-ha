"""MQTT listener: decodes public channel traffic into messages and node names."""
from __future__ import annotations

from collections import deque
from collections.abc import Callable
import logging
import ssl

import paho.mqtt.client as mqtt

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import meshdecode as md
from .const import DOMAIN, EVENT_MESSAGE, MAX_NODES, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


def parse_channels(text: str) -> dict[str, bytes | None]:
    """'LongFast=AQ==, MyChan=base64' -> {name: aes_key}."""
    keys: dict[str, bytes | None] = {}
    for part in text.replace("\n", ",").split(","):
        part = part.strip()
        if not part:
            continue
        name, _, psk = part.partition("=")
        if not name.strip():
            raise ValueError("channel name missing")
        keys[name.strip()] = md.expand_psk(psk.strip() if psk else "AQ==")
    return keys


def test_connect(host: str, port: int, username: str, password: str, tls: bool) -> None:
    """Blocking connection check for the config flow."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if username:
        client.username_pw_set(username, password)
    if tls:
        client.tls_set_context(ssl.create_default_context())
    client.connect(host, port, keepalive=10)
    rc = client.loop(timeout=5)
    client.disconnect()
    if rc != mqtt.MQTT_ERR_SUCCESS:
        raise ConnectionError(f"MQTT error {rc}")


class MeshListener:
    """Subscribes to <root>/2/e/# and keeps a rolling log of channel messages."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        host: str,
        port: int,
        username: str,
        password: str,
        root_topic: str,
        channels: str,
        tls: bool,
        history: int,
    ) -> None:
        self.hass = hass
        self.host, self.port = host, port
        self.username, self.password = username, password
        self.root = root_topic.rstrip("/")
        self.keys = parse_channels(channels)
        self.tls = tls
        self.history = history
        self.connected = False
        self.messages: deque[dict] = deque(maxlen=history)
        self.nodes: dict[str, dict] = {}
        self.messages_heard = 0
        self.packets_heard = 0
        self._seen: deque[int] = deque(maxlen=2000)
        self._seen_set: set[int] = set()
        self._listeners: list[Callable[[], None]] = []
        self._message_listeners: list[Callable[[dict], None]] = []
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")
        self._client: mqtt.Client | None = None

    # ------------------------------------------------------------ lifecycle
    async def async_start(self) -> None:
        stored = await self._store.async_load() or {}
        self.messages.extend(stored.get("messages", [])[: self.history])
        self.nodes = stored.get("nodes", {})
        self.messages_heard = stored.get("messages_heard", 0)

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"ha-{DOMAIN}-{id(self):x}")
        if self.username:
            client.username_pw_set(self.username, self.password)
        if self.tls:
            ctx = await self.hass.async_add_executor_job(ssl.create_default_context)
            client.tls_set_context(ctx)
        client.reconnect_delay_set(min_delay=5, max_delay=300)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        self._client = client
        client.connect_async(self.host, self.port, keepalive=60)
        client.loop_start()

    async def async_stop(self) -> None:
        if self._client:
            client, self._client = self._client, None
            await self.hass.async_add_executor_job(_shutdown, client)
        await self._store.async_save(self._data_to_save())

    # ------------------------------------------------------------ listeners
    @callback
    def async_add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    @callback
    def async_add_message_listener(self, cb: Callable[[dict], None]) -> Callable[[], None]:
        self._message_listeners.append(cb)
        return lambda: self._message_listeners.remove(cb)

    @callback
    def _notify(self) -> None:
        for update in list(self._listeners):
            update()

    # ------------------------------------------------------------ paho thread
    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            _LOGGER.warning("MQTT connect to %s failed: %s", self.host, reason_code)
            return
        client.subscribe(f"{self.root}/2/e/#")
        self.hass.loop.call_soon_threadsafe(self._set_connected, True)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self.hass.loop.call_soon_threadsafe(self._set_connected, False)

    def _on_message(self, client, userdata, msg) -> None:
        self.hass.loop.call_soon_threadsafe(self._handle, msg.payload)

    # ------------------------------------------------------------ event loop
    @callback
    def _set_connected(self, value: bool) -> None:
        self.connected = value
        self._notify()

    @callback
    def _handle(self, payload: bytes) -> None:
        pkt = md.decode(payload, self.keys)
        if not pkt:
            return
        self.packets_heard += 1
        # the same packet arrives once per gateway that heard it
        pid = pkt.get("id")
        if pid:
            if pid in self._seen_set:
                return
            if len(self._seen) == self._seen.maxlen:
                self._seen_set.discard(self._seen[0])
            self._seen.append(pid)
            self._seen_set.add(pid)

        data = pkt["data"]
        sender = md.node_id(pkt["from"])
        if data["portnum"] == md.PORT_NODEINFO:
            user = md.parse_user(data.get("payload", b""))
            if user.get("long_name"):
                self._remember_node(sender, user)
        elif data["portnum"] == md.PORT_TEXT and pkt.get("to") == md.BROADCAST:
            self._add_message(pkt, sender, data)

    @callback
    def _remember_node(self, sender: str, user: dict) -> None:
        self.nodes[sender] = {
            "long_name": user.get("long_name", "")[:40],
            "short_name": user.get("short_name", "")[:4],
            "seen": dt_util.utcnow().isoformat(),
        }
        if len(self.nodes) > MAX_NODES:
            oldest = sorted(self.nodes, key=lambda k: self.nodes[k]["seen"])[: len(self.nodes) - MAX_NODES]
            for key in oldest:
                del self.nodes[key]
        self._store.async_delay_save(self._data_to_save, 120)

    @callback
    def _add_message(self, pkt: dict, sender: str, data: dict) -> None:
        text = data.get("payload", b"").decode("utf-8", "replace").strip()
        if not text:
            return
        node = self.nodes.get(sender, {})
        hops = None
        if pkt.get("hop_start") is not None and pkt.get("hop_limit") is not None:
            hops = pkt["hop_start"] - pkt["hop_limit"]
        msg = {
            "time": dt_util.utcnow().isoformat(timespec="seconds"),
            "node": sender,
            "long_name": node.get("long_name") or sender,
            "short_name": node.get("short_name") or sender[-4:],
            "channel": pkt.get("channel_id"),
            "text": text[:240],
            "hops": hops,
            "snr": pkt.get("rx_snr"),
            "rssi": pkt.get("rx_rssi"),
            "gateway": pkt.get("gateway_id"),
            "reaction": bool(data.get("emoji")),
        }
        self.messages.appendleft(msg)
        self.messages_heard += 1
        self.hass.bus.async_fire(EVENT_MESSAGE, msg)
        for cb in list(self._message_listeners):
            cb(msg)
        self._store.async_delay_save(self._data_to_save, 30)
        self._notify()

    def _data_to_save(self) -> dict:
        return {
            "messages": list(self.messages),
            "nodes": self.nodes,
            "messages_heard": self.messages_heard,
        }


def _shutdown(client: mqtt.Client) -> None:
    client.disconnect()
    client.loop_stop()
