"""Local UDP discovery probe.

Broadcasts the two TP-Link discovery queries on the local network and
records which local protocol each device answers with. This lets the
integration flag devices that are TPAP-locked (cloud-only) versus ones
that still speak KLAP/AES/legacy-IOT and could use the core `tplink`
integration for local control.

Wire formats match python-kasa's Discover implementation:
- Port 9999: XOR-scrambled JSON {"system":{"get_sysinfo":{}}} (legacy IOT)
- Ports 20002/20004: fixed 16-byte magic query; reply is a 16-byte header
  followed by cleartext JSON that includes mgt_encrypt_schm.encrypt_type
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

LEGACY_PORT = 9999
NEW_PORTS = (20002, 20004)
NEW_QUERY = bytes.fromhex("020000010000000000000000463cb5d3")
LEGACY_QUERY = b'{"system":{"get_sysinfo":{}}}'
BROADCAST = "255.255.255.255"

# Local protocols python-kasa can handle today (TPAP notably absent).
LOCALLY_SUPPORTED = {"iot", "klap", "aes"}


@dataclass
class LocalInfo:
    """What a device answered on the local network."""

    ip: str
    protocol: str  # "iot", "klap", "aes", "tpap", or lowercase encrypt_type


def _xor_encrypt(plain: bytes) -> bytes:
    key = 171
    out = bytearray()
    for byte in plain:
        key ^= byte
        out.append(key)
    return bytes(out)


def _xor_decrypt(cipher: bytes) -> bytes:
    key = 171
    out = bytearray()
    for byte in cipher:
        out.append(key ^ byte)
        key = byte
    return bytes(out)


def normalize_mac(raw_mac: str | None) -> str | None:
    """Lowercase hex, no separators — for matching cloud and local records."""
    if not raw_mac:
        return None
    mac = raw_mac.replace(":", "").replace("-", "").lower()
    if len(mac) != 12:
        return None
    return mac


class _ProbeProtocol(asyncio.DatagramProtocol):
    def __init__(self, results: dict[str, LocalInfo]) -> None:
        self._results = results

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        ip = addr[0]
        try:
            if data[:2] == b"\x02\x00" and len(data) > 16:
                self._handle_new(data, ip)
            else:
                self._handle_legacy(data, ip)
        except (ValueError, KeyError, UnicodeDecodeError):
            _LOGGER.debug("Unparseable discovery reply from %s", ip)

    def _handle_new(self, data: bytes, ip: str) -> None:
        payload = json.loads(data[16:])
        result = payload.get("result") or payload
        mac = normalize_mac(result.get("mac"))
        if not mac:
            return
        existing = self._results.get(mac)
        if existing and existing.protocol == "iot":
            # A 9999 answer means the fully-supported legacy protocol is
            # available; don't let a 20002 reply demote it.
            return
        scheme = result.get("mgt_encrypt_schm") or {}
        encrypt_type = scheme.get("encrypt_type")
        if not encrypt_type:
            # Some generations report a list at the top level instead.
            encrypt_types = result.get("encrypt_type") or []
            encrypt_type = encrypt_types[0] if encrypt_types else "unknown"
        self._results[mac] = LocalInfo(ip=ip, protocol=str(encrypt_type).lower())

    def _handle_legacy(self, data: bytes, ip: str) -> None:
        sysinfo = (
            json.loads(_xor_decrypt(data)).get("system", {}).get("get_sysinfo") or {}
        )
        mac = normalize_mac(sysinfo.get("mac") or sysinfo.get("mic_mac"))
        if not mac:
            return
        # A 9999 answer always wins: it means the old fully-supported
        # cleartext/XOR protocol is still available.
        self._results[mac] = LocalInfo(ip=ip, protocol="iot")

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("Discovery socket error: %s", exc)


async def async_probe_local(timeout: float = 3.0) -> dict[str, LocalInfo]:
    """Broadcast discovery queries and collect replies for `timeout` seconds.

    Returns {normalized_mac: LocalInfo}. Failures (no broadcast capability
    in the container, etc.) return an empty dict — the probe is best-effort
    and must never break cloud polling.
    """
    results: dict[str, LocalInfo] = {}
    loop = asyncio.get_running_loop()
    try:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _ProbeProtocol(results),
            local_addr=("0.0.0.0", 0),
            allow_broadcast=True,
        )
    except OSError as err:
        _LOGGER.debug("Cannot open discovery socket: %s", err)
        return results

    try:
        legacy_query = _xor_encrypt(LEGACY_QUERY)
        for _ in range(2):  # UDP: send twice for reliability
            try:
                transport.sendto(legacy_query, (BROADCAST, LEGACY_PORT))
                for port in NEW_PORTS:
                    transport.sendto(NEW_QUERY, (BROADCAST, port))
            except OSError as err:
                _LOGGER.debug("Discovery send failed: %s", err)
                break
            await asyncio.sleep(timeout / 2)
    finally:
        transport.close()

    return results
