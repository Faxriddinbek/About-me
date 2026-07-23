# Portfolio Backend

Production-grade **FastAPI** backend for a bilingual (Uzbek default, English
secondary) personal portfolio website. The frontend is a separate static site
(deployed on Vercel); this API serves its data.

This repository currently contains the **foundation only** — configuration,
database plumbing, logging, error handling, and the application bootstrap.
Routes, models, and business logic are added in later steps.

## Architecture

The code is organised in layers so HTTP concerns, business logic, and
persistence stay decoupled and independently testable:

```
api  ->  services  ->  repositories  ->  db
```

| Path                 | Responsibility                                              |
| -------------------- | ----------------------------------------------------------- |
| `app/core/`          | Config, structured logging, domain exceptions + handlers    |
| `app/db/`            | Declarative base (audited columns) + async engine/session   |
| `app/api/`           | Routers, shared dependencies, versioned endpoints (`/v1`)   |
| `app/models/`        | SQLAlchemy ORM models (later steps)                         |
| `app/schemas/`       | Pydantic request/response schemas (later steps)             |
| `app/repositories/`  | Data-access queries (later steps)                           |
| `app/services/`      | Business logic (later steps)                                |

Key traits: fully typed, async throughout (no sync DB calls), SQLAlchemy 2.0
style (`DeclarativeBase` / `Mapped` / `mapped_column`), and all configuration
sourced from a single validated `Settings` object.

## Requirements

- Python 3.12+
- A virtual environment (one already exists at `.venv/`)

## Setup

```bash
# 1. Activate the virtual environment
#    Windows (PowerShell):
.venv\Scripts\Activate.ps1
#    macOS / Linux:
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create your local configuration
cp .env.example .env   # then edit as needed
```

## Running

```bash
uvicorn app.main:app --reload
```

- Health check: <http://127.0.0.1:8000/health>
- Interactive docs (dev only): <http://127.0.0.1:8000/docs>
- API v1 is mounted under `/api/v1`.

In production (`ENVIRONMENT=prod`) the `/docs`, `/redoc`, and `/openapi.json`
endpoints are disabled, logs are emitted as JSON, and the app refuses to start
unless required secrets (`ADMIN_TOKEN`, a real `DATABASE_URL`) are configured.

## Testing & linting

```bash
pytest          # runs the smoke tests against an in-memory SQLite database
ruff check .    # lint
ruff format .   # format
```

## Configuration

Every setting is documented in [`.env.example`](.env.example). Summary:

| Variable             | Required | Description                                         |
| -------------------- | -------- | --------------------------------------------------- |
| `APP_NAME`           | no       | Display name used in docs and logs                  |
| `APP_VERSION`        | no       | Version string returned by `/health`                |
| `ENVIRONMENT`        | no       | `dev` (default) or `prod`                           |
| `DEBUG`              | no       | Verbose logging / SQL echo                          |
| `DATABASE_URL`       | prod     | Async DSN; SQLite fallback for local dev            |
| `CORS_ORIGINS`       | no       | Comma-separated allowed frontend origins            |
| `ADMIN_TOKEN`        | prod     | Bearer token guarding write endpoints               |
| `TELEGRAM_BOT_TOKEN` | no       | Enables Telegram notifications (later steps)        |
| `TELEGRAM_CHAT_ID`   | no       | Target chat for Telegram notifications              |

Error responses use a consistent envelope:

```json
{ "error": { "code": "not_found", "message": "…", "detail": null } }
```
