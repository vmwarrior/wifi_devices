# wifi_devices

Monitors the WiFi/LAN network for connected devices and records, per device,
**when it was first seen** and **when it was last seen**. New (never-before-seen)
devices are flagged in the log so you can spot anything unexpected joining the
network.

## How it works

- **Discovery** — `scanner.py` runs an active ARP scan (via [scapy](https://scapy.net))
  against the local subnet, sending ARP requests to every address and collecting
  replies. This finds all devices, including idle ones that aren't currently
  exchanging traffic.
- **Storage** — `db.py` keeps a SQLite database (`data/devices.db`) with one row
  per device (keyed by MAC): last IP, hostname (reverse DNS, best-effort),
  vendor (from the MAC OUI), `first_seen`, `last_seen`, and `times_seen`.
- **Detection** — any MAC not already in the database is logged as a
  `NEW DEVICE` warning in `data/monitor.log`.

## Setup

```bash
# from the project root, using the provided virtualenv
.venv/bin/pip install -r requirements.txt
```

The first vendor lookup downloads an offline MAC OUI database (needs internet
once); after that it's cached locally.

## Usage

ARP scanning needs raw sockets, so a **scan must run as root**:

```bash
sudo .venv/bin/python wifi_monitor.py              # scan auto-detected subnet
sudo .venv/bin/python wifi_monitor.py --subnet 192.168.0.0/24
sudo .venv/bin/python wifi_monitor.py -v           # also print to stdout
```

Reading the stored data does **not** need root:

```bash
.venv/bin/python wifi_monitor.py --list            # all devices, newest first
.venv/bin/python wifi_monitor.py --new             # devices first seen in last 24h
```

You can also query the SQLite DB directly:

```bash
sqlite3 data/devices.db "SELECT mac, vendor, first_seen, last_seen FROM devices;"
```

## Scheduling

Run it on a schedule with **root's** crontab so it has scan privileges:

```bash
sudo crontab -e
```

Add (scan every 4 hours — at 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 — to
capture devices that are only online at different times of day):

```cron
0 */4 * * * /home/victor/wifi_devices/.venv/bin/python /home/victor/wifi_devices/wifi_monitor.py
```

This entry is already installed in root's crontab (`sudo crontab -l` to verify).
Adjust the schedule by editing it with `sudo crontab -e`.

Because cron isn't a TTY, output goes to `data/monitor.log` only. Watch for new
devices with:

```bash
grep "NEW DEVICE" data/monitor.log
# or live:
tail -f data/monitor.log
```

> Note: files under `data/` will be owned by root when scans run via sudo/cron.
> The `--list`/`--new` read commands still work as your normal user because the
> SQLite DB is world-readable.

## Files

| File               | Purpose                                          |
| ------------------ | ------------------------------------------------ |
| `wifi_monitor.py`  | CLI entry point: scan, `--list`, `--new`         |
| `scanner.py`       | Subnet detection + ARP scan + vendor/hostname    |
| `db.py`            | SQLite storage of device sightings               |
| `requirements.txt` | Python dependencies                              |
| `data/`            | Runtime DB + log (git-ignored)                   |
