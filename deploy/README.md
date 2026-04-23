# Deployment — nightly cron on a Linux VM

This directory has the templates for running the in-season daily update on a schedule. Pick one of the two options below.

## Prerequisites

1. Clone the repo and run the one-time backfill (takes ~1 hour for 2015–current):

   ```bash
   git clone <repo-url> /opt/baseball
   cd /opt/baseball
   python3.11 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/pip install -e .
   cp .env.example .env   # optional — tweak BASEBALL_DUCKDB_MEMORY_LIMIT for 8 GB VMs
   .venv/bin/baseball backfill --start-season 2015 --end-season $(date +%Y)
   .venv/bin/baseball rebuild-derived
   ```

2. Create a dedicated user + log directory:

   ```bash
   sudo useradd --system --create-home --shell /usr/sbin/nologin baseball
   sudo mkdir -p /var/log/baseball
   sudo chown -R baseball:baseball /opt/baseball /var/log/baseball
   ```

## Option A — systemd timer (recommended)

Native DST handling, journal integration, and boot-time catch-up if the VM is offline at the scheduled time.

```bash
sudo cp deploy/systemd/baseball-daily-update.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now baseball-daily-update.timer
```

Verify:

```bash
systemctl list-timers baseball-daily-update.timer
journalctl -u baseball-daily-update.service --since today
```

Manual one-shot run (for smoke testing):

```bash
sudo systemctl start baseball-daily-update.service
```

## Option B — crontab

Simpler, but no timezone awareness — the example runs at **12:00 UTC**, which is ~08:00 ET during EDT and ~07:00 ET during EST. If that's fine for your use, install with:

```bash
sudo -u baseball crontab deploy/crontab.example
```

Verify:

```bash
sudo -u baseball crontab -l
```

## What the daily job actually does

`baseball daily-update --days 2` (the command both options run) does:

1. Ingests each of the last 2 calendar days. Any day whose week-key is already in the manifest is skipped in <1 s.
2. If any fresh pitches landed, rebuilds all derived Parquet tables so `matchup_edges` and the `_shrunk` columns reflect the latest data.
3. Logs to stderr and (if `BASEBALL_DAILY_LOG_DIR` is set) to a rotated file.

Typical in-season runtime: **30–90 seconds**. Off-season runs exit in <1 s because no pitches come back.

## Troubleshooting

- **"No raw Statcast parquet files found"** — you didn't run the one-time backfill yet. See Prerequisites step 1.
- **Savant 403/timeout** — temporary; the catch-up `--days 2` next night will fill the gap automatically.
- **OOM during rebuild** — lower `BASEBALL_DUCKDB_MEMORY_LIMIT` in the service file (e.g., `2GB`).
- **Logs piling up** — the loguru file sink rotates every 7 days and keeps 30 days; the raw `cron.log` (Option B) needs your own `logrotate` entry.
