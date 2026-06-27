"""SQLite storage for observed network devices.

One row per device (keyed by MAC address) tracking when it was first and
last seen on the network, plus the most recent IP/hostname/vendor.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    mac        TEXT PRIMARY KEY,
    ip         TEXT,
    hostname   TEXT,
    vendor     TEXT,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    times_seen INTEGER NOT NULL DEFAULT 1
);
"""


@dataclass
class Device:
    mac: str
    ip: str | None = None
    hostname: str | None = None
    vendor: str | None = None


def utcnow() -> str:
    """Current time as an ISO-8601 UTC string (sortable, timezone-aware)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DeviceStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record(self, device: Device, seen_at: str | None = None) -> bool:
        """Insert or update a device sighting.

        Returns True if this MAC had never been seen before (a new device).
        """
        seen_at = seen_at or utcnow()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT mac FROM devices WHERE mac = ?", (device.mac,)
            ).fetchone()
            is_new = row is None
            if is_new:
                conn.execute(
                    """INSERT INTO devices
                       (mac, ip, hostname, vendor, first_seen, last_seen, times_seen)
                       VALUES (?, ?, ?, ?, ?, ?, 1)""",
                    (device.mac, device.ip, device.hostname, device.vendor,
                     seen_at, seen_at),
                )
            else:
                # COALESCE keeps the previous value when the new scan didn't
                # resolve a hostname/vendor this time.
                conn.execute(
                    """UPDATE devices SET
                           ip = ?,
                           hostname = COALESCE(?, hostname),
                           vendor = COALESCE(?, vendor),
                           last_seen = ?,
                           times_seen = times_seen + 1
                       WHERE mac = ?""",
                    (device.ip, device.hostname, device.vendor, seen_at,
                     device.mac),
                )
            return is_new

    def all_devices(self, order_by: str = "last_seen DESC") -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                f"SELECT * FROM devices ORDER BY {order_by}"
            ).fetchall()
