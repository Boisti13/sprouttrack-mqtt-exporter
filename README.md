# Sprout Track -> Home Assistant (MQTT Discovery) Exporter

This project reads Sprout Track's SQLite database and publishes a small set of derived metrics to MQTT, including Home Assistant MQTT Discovery so entities appear automatically.

## What it publishes
For a selected baby, it publishes retained MQTT sensor states under:

- `sprouttrack/<BABY_ID>/sensor/<key>/state`
- availability (LWT): `sprouttrack/<BABY_ID>/availability`
- last error (if any): `sprouttrack/<BABY_ID>/last_error`

Sensors (keys):
- `time_since_feed` (HH:MM)
- `time_since_diaper` (HH:MM)
- `last_feed_side` (LEFT/RIGHT/BOTH)
- `next_feed_side` (LEFT/RIGHT)
- `sleeping` (on/off)
- `sleep_state` (AWAKE/NAP/NIGHT_SLEEP)
- `time_since_sleep_start` (HH:MM)
- `time_since_sleep_end` (HH:MM)
- `feeds_today` (count)
- `diapers_today` (count)
- `sleep_today` (HH:MM total)

Note: `last_diaper_time` is intentionally **not** published.

## Quick start (recommended)
Run the interactive setup script from the project directory. It will:
- detect/ask for the DB path
- list babies and let you pick one
- ask for MQTT host/port and credentials
- ask for poll interval
- write `config.yaml` + `.secrets.env`

```bash
cd sprouttrack-mqtt-exporter
bash scripts/setup.sh
```

Then run the exporter:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m sprouttrack_exporter --config config.yaml --secrets .secrets.env
```

## Configuration
- `config.yaml` contains non-secret settings.
- `.secrets.env` contains secrets (MQTT username/password). It is gitignored.

You can also override anything via CLI flags. Run:

```bash
python -m sprouttrack_exporter --help
```

## Systemd (optional)
A template is provided in `systemd/`. Adjust paths and install it on your host if you want it to start on boot.
