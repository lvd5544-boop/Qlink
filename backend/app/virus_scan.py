"""Virus scanning for Evidence Vault uploads.

Default: local EICAR signature detection (always on).
Optional: ClamAV daemon via CLAMAV_HOST:CLAMAV_PORT when VIRUS_SCAN_ENABLED=true.
"""

from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Standard EICAR test file signature (safe test string used by AV vendors).
EICAR_SIGNATURE = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


@dataclass(frozen=True)
class ScanResult:
    clean: bool
    engine: str
    detail: str | None = None


def virus_scan_enabled() -> bool:
    raw = os.getenv("VIRUS_SCAN_ENABLED", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _scan_eicar(data: bytes) -> ScanResult:
    if EICAR_SIGNATURE in data:
        return ScanResult(clean=False, engine="eicar_signature", detail="eicar_test_signature")
    return ScanResult(clean=True, engine="eicar_signature")


def _scan_clamav(data: bytes) -> ScanResult | None:
    host = (os.getenv("CLAMAV_HOST") or "").strip()
    if not host:
        mode = (os.getenv("VIRUS_SCAN_FAIL_MODE") or "closed").strip().lower()
        if mode in {"closed", "fail_closed", "reject"}:
            return ScanResult(clean=False, engine="clamav", detail="scanner_not_configured")
        return None
    port = int(os.getenv("CLAMAV_PORT", "3310"))
    timeout = float(os.getenv("CLAMAV_TIMEOUT_SECONDS", "5"))
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            # INSTREAM protocol
            sock.sendall(b"zINSTREAM\0")
            chunk_size = 2048
            for offset in range(0, len(data), chunk_size):
                chunk = data[offset : offset + chunk_size]
                sock.sendall(len(chunk).to_bytes(4, "big") + chunk)
            sock.sendall((0).to_bytes(4, "big"))
            response = b""
            while True:
                part = sock.recv(4096)
                if not part:
                    break
                response += part
                if b"\0" in response:
                    break
        text = response.decode("utf-8", errors="replace")
        if "FOUND" in text and "OK" not in text.split("FOUND")[0][-10:]:
            # Typical: "stream: Eicar-Test-Signature FOUND"
            if "FOUND" in text:
                return ScanResult(clean=False, engine="clamav", detail=text.strip())
        if "OK" in text:
            return ScanResult(clean=True, engine="clamav")
        logger.warning("unexpected clamav response: %s", text[:200])
        mode = (os.getenv("VIRUS_SCAN_FAIL_MODE") or "closed").strip().lower()
        if mode in {"closed", "fail_closed", "reject"}:
            return ScanResult(clean=False, engine="clamav", detail="unexpected_scanner_response")
        return None
    except OSError as exc:
        mode = (os.getenv("VIRUS_SCAN_FAIL_MODE") or "closed").strip().lower()
        logger.warning("clamav unavailable: %s", type(exc).__name__)
        if mode in {"closed", "fail_closed", "reject"}:
            return ScanResult(clean=False, engine="clamav", detail="scanner_unavailable")
        return None


def scan_bytes(data: bytes) -> ScanResult:
    """Scan upload bytes. Always runs EICAR; optionally ClamAV."""
    if not virus_scan_enabled():
        return ScanResult(clean=True, engine="disabled")
    eicar = _scan_eicar(data)
    if not eicar.clean:
        return eicar
    clam = _scan_clamav(data)
    if clam is not None:
        return clam
    return eicar
