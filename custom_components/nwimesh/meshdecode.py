"""Minimal Meshtastic MQTT decoder (no protobuf/meshtastic dependency).

Decodes ServiceEnvelope -> MeshPacket -> Data for the few ports we use and
decrypts channel traffic with the channel PSK (AES-CTR, same as firmware).
"""
from __future__ import annotations

import base64
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

BROADCAST = 0xFFFFFFFF
PORT_TEXT = 1
PORT_NODEINFO = 4

# firmware default channel key ("AQ==" == index 1)
_DEFAULT_PSK = bytes.fromhex("d4f1bb3a20290759f0bcffabcf4e6901")


def expand_psk(psk_b64: str) -> bytes | None:
    """Turn a channel PSK as shown in the app (base64) into an AES key."""
    raw = base64.b64decode(psk_b64.strip() or "AQ==")
    if len(raw) == 0:
        return None  # unencrypted channel
    if len(raw) == 1:
        if raw[0] == 0:
            return None
        return _DEFAULT_PSK[:-1] + bytes([(_DEFAULT_PSK[-1] + raw[0] - 1) & 0xFF])
    if len(raw) in (16, 32):
        return raw
    raise ValueError("PSK must be 1, 16 or 32 bytes")


def _varint(b: bytes, i: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        x = b[i]
        i += 1
        result |= (x & 0x7F) << shift
        shift += 7
        if x < 0x80:
            return result, i


def _fields(b: bytes):
    i, n = 0, len(b)
    while i < n:
        key, i = _varint(b, i)
        num, wire = key >> 3, key & 7
        if wire == 0:
            val, i = _varint(b, i)
        elif wire == 1:
            val, i = b[i:i + 8], i + 8
        elif wire == 2:
            ln, i = _varint(b, i)
            val, i = b[i:i + ln], i + ln
        elif wire == 5:
            val, i = b[i:i + 4], i + 4
        else:
            raise ValueError(f"unsupported wire type {wire}")
        yield num, wire, val


def _u32(v: bytes) -> int:
    return struct.unpack("<I", v)[0]


def _signed(v: int) -> int:
    return v - (1 << 64) if v >= 1 << 63 else v


def decrypt(key: bytes, packet_id: int, sender: int, data: bytes) -> bytes:
    nonce = struct.pack("<QI", packet_id, sender) + b"\x00" * 4
    dec = Cipher(algorithms.AES(key), modes.CTR(nonce)).decryptor()
    return dec.update(data) + dec.finalize()


def parse_envelope(payload: bytes) -> dict | None:
    """ServiceEnvelope -> dict with the MeshPacket fields we care about."""
    env: dict = {}
    for num, _, val in _fields(payload):
        if num == 1:
            env["packet"] = val
        elif num == 2:
            env["channel_id"] = val.decode("utf-8", "replace")
        elif num == 3:
            env["gateway_id"] = val.decode("utf-8", "replace")
    if "packet" not in env:
        return None

    pkt: dict = {"channel_id": env.get("channel_id"), "gateway_id": env.get("gateway_id")}
    for num, wire, val in _fields(env["packet"]):
        if num == 1:
            pkt["from"] = _u32(val)
        elif num == 2:
            pkt["to"] = _u32(val)
        elif num == 3:
            pkt["channel"] = val
        elif num == 4:
            pkt["decoded"] = val
        elif num == 5:
            pkt["encrypted"] = val
        elif num == 6:
            pkt["id"] = _u32(val)
        elif num == 7:
            pkt["rx_time"] = _u32(val)
        elif num == 8:
            pkt["rx_snr"] = round(struct.unpack("<f", val)[0], 2)
        elif num == 9:
            pkt["hop_limit"] = val
        elif num == 12:
            pkt["rx_rssi"] = _signed(val)
        elif num == 14:
            pkt["via_mqtt"] = bool(val)
        elif num == 15:
            pkt["hop_start"] = val
    return pkt


def parse_data(raw: bytes) -> dict | None:
    data: dict = {}
    try:
        for num, wire, val in _fields(raw):
            if num == 1 and wire == 0:
                data["portnum"] = val
            elif num == 2 and wire == 2:
                data["payload"] = val
            elif num == 8 and wire == 5:
                data["emoji"] = _u32(val)
            elif num == 7 and wire == 5:
                data["reply_id"] = _u32(val)
    except (IndexError, ValueError):
        return None
    return data if "portnum" in data else None


def parse_user(raw: bytes) -> dict:
    user: dict = {}
    for num, wire, val in _fields(raw):
        if wire != 2:
            continue
        if num == 1:
            user["id"] = val.decode("utf-8", "replace")
        elif num == 2:
            user["long_name"] = val.decode("utf-8", "replace")
        elif num == 3:
            user["short_name"] = val.decode("utf-8", "replace")
    return user


def decode(payload: bytes, keys: dict[str, bytes | None]) -> dict | None:
    """Full decode. keys maps channel name -> AES key (None = plaintext).

    Returns the packet dict with "data" added, or None when it can't be read
    (unknown channel, PKI direct message, garbage).
    """
    try:
        pkt = parse_envelope(payload)
    except (IndexError, ValueError, struct.error):
        return None
    if not pkt or "from" not in pkt:
        return None
    if "decoded" in pkt:
        data = parse_data(pkt["decoded"])
    elif "encrypted" in pkt and pkt.get("channel_id") in keys:
        key = keys[pkt["channel_id"]]
        if key is None or "id" not in pkt:
            return None
        data = parse_data(decrypt(key, pkt["id"], pkt["from"], pkt["encrypted"]))
    else:
        return None
    if not data:
        return None
    pkt["data"] = data
    return pkt


def node_id(num: int) -> str:
    return f"!{num:08x}"
