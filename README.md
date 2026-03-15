# Local Automated Trading Platform

Phase 1 backend foundation for a local automated trading workstation with:

- independent core engines
- internal pub/sub event bus
- FastAPI system API and WebSocket event stream
- SQLAlchemy-backed persistence
- health and status monitoring
- startup script for local orchestration

## Project Structure

```text
core/
  data_engine/
  scanner_engine/
  strategy_engine/
  execution_engine/
  risk_engine/
  backtest_engine/
  analytics_engine/
adapters/
  brokers/
  data_providers/
gui/
database/
config/
utils/
logs/
scripts/
```

## Quick Start

1. Create a Python 3.11+ virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Optional editable install: `pip install -e .`
4. Optionally start Redis/PostgreSQL via `docker compose up -d`.
5. Copy values from `env.example.txt` into your environment.
6. Start the platform with `python scripts/start_platform.py`.
7. Open `http://127.0.0.1:8000/` for the local dark health dashboard.

Windows helpers:

- PowerShell: `.\scripts\start_platform.ps1`
- Command Prompt: `scripts\start_platform.bat`
- One-click launcher with Git auto update: `.\Open Trading Platform.bat`
- Clone or update from GitHub, then launch: `.\Install Or Update From GitHub.bat`

Smoke check:

- `python scripts/smoke_check.py`
- `python scripts/smoke_check.py http://127.0.0.1:8000`

## Phase 1 Endpoints

- `GET /health`
- `GET /`
- `GET /dashboard/health`
- `GET /system/overview`
- `GET /system/status`
- `GET /system/engines`
- `POST /system/engines/{engine_name}/start`
- `POST /system/engines/{engine_name}/stop`
- `POST /system/engines/{engine_name}/restart`
- `GET /system/events/recent`
- `WS /ws/events`

## Notes

- The preferred runtime stack is PostgreSQL + TimescaleDB + Redis.
- For local bootstrap, the app can fall back to SQLite and in-memory pub/sub.
- The data engine publishes synthetic sample ticks in Phase 1 so the platform shows live event flow before market integrations are added in Phase 2.
- `system_snapshots` stores overview snapshots that can later feed the GUI dashboard.
- By default, local API credentials and user preferences are stored in a machine-local SQLite file outside the repo so they are not committed to Git.

## GitHub Sharing And Auto Update

Use this when you want to share the app with another machine through GitHub while keeping each machine's API keys local-only.

1. Initialize the local project as a git repo and connect it to your remote.
2. Push the code to your GitHub repository.
3. On each computer, clone the repository instead of copying the folder manually.
4. Launch the app with `Open Trading Platform.bat`.

Helper scripts:

- `scripts/publish_to_github.ps1`: initialize the current folder as a repo, connect it to `https://github.com/MyNameisntZ/hftv2.git`, commit, and push to `main`
- `scripts/bootstrap_from_github.ps1`: clone or update the GitHub repo into a target folder and launch it
- `Install Or Update From GitHub.bat`: Windows wrapper for the GitHub bootstrap script

What the launcher does:

- starts the backend
- opens the dashboard after the health check succeeds
- checks the tracked Git branch for new commits every 60 seconds by default
- runs `git pull --ff-only` when the remote is ahead
- restarts the backend after a successful update
- lets the browser auto-reload when the backend instance changes

Local-only secrets:

- API keys entered in the frontend are stored in the local preferences database, not in tracked source files
- the default local database path lives outside the repository, so Git pushes do not include saved credentials
- if you already used the old in-repo SQLite database, the app migrates it once into the new machine-local path on startup

Optional launcher environment variables:

- `GIT_AUTO_UPDATE_ENABLED=true`
- `GIT_AUTO_UPDATE_INTERVAL_SECONDS=60`

