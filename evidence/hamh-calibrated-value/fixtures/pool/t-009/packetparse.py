"""Binary packet parser (task fixture t-009)."""

import struct

MAGIC = 0xA5A5


def parse_packet(data: bytes) -> dict:
    """Parse a packet per the documented wire format (big-endian)."""
    if len(data) < 7:
        raise ValueError("packet too short")
    magic, version, flags, payload_len = struct.unpack(">HBBI", data[:8])
    if magic != MAGIC:
        raise ValueError("bad magic")
    if len(data) < 8 + payload_len:
        raise ValueError("truncated payload")
    payload = data[8 : 8 + payload_len]
    checksum = data[8 + payload_len]
    total = sum(data[: 8 + payload_len]) & 0xFF
    return {
        "version": version,
        "flags": flags,
        "payload": payload,
        "checksum_ok": checksum == total,
    }
