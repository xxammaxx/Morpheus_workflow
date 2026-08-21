"""Tests for packetparse (task fixture t-009)."""

import struct

import pytest

from packetparse import parse_packet


def _build(version=1, flags=0, payload=b"hello", corrupt_checksum=False, magic=0xA5A5):
    # wire format: magic 2B + version 1B + flags 1B + payload_len 2B (big-endian)
    head = struct.pack(">HBBH", magic, version, flags, len(payload))
    body = head + payload
    checksum = sum(body) & 0xFF
    if corrupt_checksum:
        checksum = (checksum + 1) & 0xFF
    return body + bytes([checksum])


def test_valid_packet():
    pkt = _build(version=2, flags=3, payload=b"hello world")
    r = parse_packet(pkt)
    assert r["version"] == 2
    assert r["flags"] == 3
    assert r["payload"] == b"hello world"
    assert r["checksum_ok"] is True


def test_empty_payload():
    r = parse_packet(_build(payload=b""))
    assert r["payload"] == b""
    assert r["checksum_ok"] is True


def test_binary_payload():
    payload = bytes(range(256))
    r = parse_packet(_build(payload=payload))
    assert r["payload"] == payload
    assert r["checksum_ok"] is True


def test_bad_magic():
    with pytest.raises(ValueError):
        parse_packet(_build(magic=0x1234))


def test_corrupt_checksum_detected():
    r = parse_packet(_build(payload=b"abc", corrupt_checksum=True))
    assert r["checksum_ok"] is False


def test_truncated_payload():
    pkt = _build(payload=b"0123456789")
    with pytest.raises(ValueError):
        parse_packet(pkt[:-2])


def test_too_short():
    with pytest.raises(ValueError):
        parse_packet(b"\xa5\xa5\x01")


def test_large_payload_length_boundary():
    # payload_len field is 2 bytes (max 65535); parser must not misread it
    payload = b"x" * 300  # exceeds a single byte, catches endianness bugs
    r = parse_packet(_build(payload=payload))
    assert r["payload"] == payload
