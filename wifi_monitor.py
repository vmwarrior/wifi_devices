#!/usr/bin/env python3
"""WiFi device monitor.

Scans the local network for connected devices and records, per device,
when it was first seen and when it was last seen. New (never-before-seen)
devices are highlighted in the log.

Usage:
    sudo .venv/bin/python wifi_monitor.py            # run one scan
    sudo .venv/bin/python wifi_monitor.py --subnet 192.168.0.0/24
    .venv/bin/python wifi_monitor.py --list          # show stored devices
    .venv/bin/python wifi_monitor.py --new           # devices first seen in last 24h
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from db import DeviceStore
from scanner import detect_subnet, scan

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "devices.db"
LOG_PATH = DATA_DIR / "monitor.log"

log = logging.getLogger("wifi_monitor")


def setup_logging(verbose: bool) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = []
    try:
        handlers.append(logging.FileHandler(LOG_PATH))
    except OSError:
        # e.g. log file owned by root from a sudo scan while running --list
        # as a normal user. Fall back to stdout-only logging.
        pass
    if not handlers or verbose or sys.stdout.isatty():
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def run_scan(subnet: str | None) -> int:
    if os.geteuid() != 0:
        log.error("ARP scanning needs root. Re-run with sudo.")
        return 1

    interface = None
    if subnet is None:
        interface, subnet = detect_subnet()
    log.info("Scanning %s%s", subnet,
             f" on {interface}" if interface else "")

    store = DeviceStore(DB_PATH)
    devices = scan(subnet)
    new_count = 0
    for device in devices:
        is_new = store.record(device)
        if is_new:
            new_count += 1
            log.warning(
                "NEW DEVICE  mac=%s ip=%s vendor=%s hostname=%s",
                device.mac, device.ip, device.vendor or "?",
                device.hostname or "?",
            )
    log.info("Scan complete: %d device(s) online, %d new",
             len(devices), new_count)
    return 0


def show_devices(only_new_hours: int | None) -> int:
    store = DeviceStore(DB_PATH)
    rows = store.all_devices(order_by="first_seen DESC")
    if only_new_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=only_new_hours)
        rows = [r for r in rows
                if datetime.fromisoformat(r["first_seen"]) >= cutoff]

    if not rows:
        print("No devices recorded yet.")
        return 0

    header = f"{'MAC':<18} {'IP':<15} {'Vendor':<22} {'First seen':<20} {'Last seen':<20} Seen"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['mac']:<18} {r['ip'] or '':<15} "
              f"{(r['vendor'] or '')[:22]:<22} "
              f"{r['first_seen']:<20} {r['last_seen']:<20} {r['times_seen']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--subnet", help="CIDR to scan, e.g. 192.168.0.0/24 "
                        "(auto-detected if omitted)")
    parser.add_argument("--list", action="store_true",
                        help="List all stored devices and exit")
    parser.add_argument("--new", action="store_true",
                        help="List devices first seen in the last 24h and exit")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Also log to stdout")
    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.list:
        return show_devices(None)
    if args.new:
        return show_devices(24)
    return run_scan(args.subnet)


if __name__ == "__main__":
    raise SystemExit(main())
