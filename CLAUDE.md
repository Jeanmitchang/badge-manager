# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Badge Manager v2** — a multi-user RFID badge access control management system. Users manage RFID badges, encode them to MCT files via a Wine-wrapped Windows executable (`vigik_loader_cli.exe`), and download the results. A 3-tier RBAC model controls access: **superadmin → admin → user**.

Stack: Python/FastAPI backend, SQLite database, vanilla JS single-page PWA frontend. No build step required.

## Commands

```bash
# First-time initialization (creates DB, superadmin account, directories)
python3 setup_v2.py

# Run the server (use virtualenv if present)
source venv/bin/activate
python3 server_v2.py

# Emergency recovery (reset superadmin password, unlock account, generate JWT)
python3 emergency_v2.py

# Manual database backup
./backup.sh

# Systemd service management (replace <user> with the system user)
sudo systemctl start|stop|restart|status vigik-server-v2@<user>
sudo journalctl -u vigik-server-v2@<user> -f
```

No test suite or linter is configured. Manual testing against the running server is the primary approach.

## Architecture

### Core Files

| File | Purpose |
|------|---------|
| `server_v2.py` | FastAPI app — all endpoints, auth middleware, background tasks |
| `database.py` | SQLite ORM layer — schema, queries, context manager transactions |
| `static_v2/app.js` | Frontend SPA — all UI logic, views, API calls |
| `static_v2/index.html` | HTML shell + embedded CSS (PWA manifest) |
| `setup_v2.py` | One-time initialization |
| `emergency_v2.py` | SSH-only recovery procedures |

### Database Layer (`database.py`)

Uses a context manager pattern for all transactions:
```python
with db() as conn:
    conn.execute(...)
```
Rolls back automatically on exception. Foreign keys are enforced. Primary keys are UUIDs. Timestamps stored as ISO UTC strings.

Key tables: `users`, `groups`, `badges`, `mct_history`, `requests`, `messages`, `notifications`, `activity_log`, `config`.

### Authentication

Custom HS256 JWT implementation (no external library). Tokens issued at `/api/login`, passed as `Authorization: Bearer <token>`. Secrets and TTL are configured via `.env` / database `config` table.

### Badge Encoding Pipeline

1. User calls `POST /api/badges/{bid}/encode`
2. Daily quota and concurrent queue (max 5) are checked
3. Wine subprocess runs: `wine vigik_loader_cli.exe -c cert.txt -u {UID} -o json -f {tmp.json}`
4. JSON → MFD (1024-byte MiFare binary) → MCT text format
5. MCT file saved under `mct_output/{owner_id}/` with expiration (default 84 hours)
6. File returned as download; event logged to `activity_log`

### Background Tasks (in `server_v2.py`)

- **Watchdog** (every 60s): monitors RAM/CPU/disk, alerts superadmin on thresholds
- **Cleanup loop** (hourly): purges expired MCT files

### Frontend

Single-page app with no framework and no build step. Routing is client-side; the server returns `index.html` for all unmatched paths. Auth token stored in `localStorage`. Views are rendered by JS functions that inject HTML into the DOM.

## Configuration

Primary config in `.env` file (see `.env.example` for template):
- `VIGIK_JWT_SECRET` — JWT signing secret (auto-generated if absent, must be set for production)
- `VIGIK_PORT` — server port (default 8766)
- `VIGIK_EXE` — path to `vigik_loader_cli.exe`
- `VIGIK_CERT` — path to Vigik cert file for encoding
- `VIGIK_MCT` — MCT output directory
- `VIGIK_DB_PATH` — SQLite database file path (default `./data/badge_manager.db`)
- `VIGIK_SSL_CERT` / `VIGIK_SSL_KEY` — TLS certificate paths (empty = HTTP only)
- `VIGIK_CORS_ORIGINS` — allowed CORS origins, comma-separated (empty = same-origin only)

Runtime config stored in the `config` database table (badge quotas, MCT daily limits, JWT TTL, etc.).

## Key Conventions

- Code comments and some user-facing messages are in **French**
- Section headers use `# ─── SECTION ───` style in both Python files
- Soft-delete pattern: deleted users are marked with a `deleted_at` timestamp and await superadmin approval before permanent removal
- All user actions are written to `activity_log` (auditing is non-optional)
- `mct_badges.keys` in the repo root is a generated/temporary file — not source code
