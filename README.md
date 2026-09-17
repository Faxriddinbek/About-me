# Portfolio Backend

Production-grade **FastAPI** backend for a bilingual (Uzbek default, English
secondary) personal portfolio website. It serves project, media (photo/video),
and contact data to a separate static frontend (deployed on Vercel). It is
fully typed, async throughout, layered, and tested.

- **Public API:** list/read projects and media, submit a contact message.
- **Admin API:** manage projects/media and read contact messages, guarded by a
  constant-time token check.
- **Ops:** structured JSON logs, a consistent error envelope, DB migrations,
  per-IP rate limiting, and a `/health` probe.

## Architecture

Strict one-directional layering keeps HTTP, business logic, and persistence
decoupled and independently testable:

```
        HTTP request
             │
             ▼
   ┌───────────────────┐   app/api/         routers: parse input, call one
   │   API (routers)   │                    service method, return. No logic.
   └───────────────────┘   app/api/deps.py  DI wiring + auth + params
             │
             ▼
   ┌───────────────────┐   app/services/    business rules; raises domain
   │     Services      │                    errors; never imports FastAPI
   └───────────────────┘
             │
             ▼
   ┌───────────────────┐   app/repositories/  pure async data access;
   │   Repositories    │                      returns models, never schemas
   └───────────────────┘
             │
             ▼
   ┌───────────────────┐   app/models/      SQLAlchemy 2.0 ORM models
   │   Models (DB)     │   app/db/          engine, session, declarative base
   └───────────────────┘
```

Cross-cutting: `app/core/` (settings, structured logging, error handling),
`app/schemas/` (Pydantic v2 request/response DTOs, incl. language resolution and
the generic `Page[T]`). Dependencies flow **down only** — a repository never
imports a service, a service never imports FastAPI.

## Requirements

- Python 3.12+ (for the local, non-Docker path), or
- Docker + Docker Compose (recommended for local dev)

## Local setup — Docker (recommended)

Postgres + the API with hot reload, one command:

```bash
docker compose up --build
```

- API: <http://localhost:8000> · docs: <http://localhost:8000/docs> · health: <http://localhost:8000/health>
- Migrations run automatically before the server starts; the API waits until
  Postgres is healthy.

## Local setup — without Docker (SQLite)

```bash
# From the project root, with the virtualenv activated:
#   Windows (PowerShell):  .venv\Scripts\Activate.ps1
#   macOS / Linux:         source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # defaults use a local SQLite database
alembic upgrade head          # create the schema
uvicorn app.main:app --reload
```

## Environment variables

Every variable is documented in [`.env.example`](.env.example).

| Name                 | Required            | Default                             | Description                                                                 |
| -------------------- | ------------------- | ----------------------------------- | --------------------------------------------------------------------------- |
| `APP_NAME`           | no                  | `Portfolio API`                     | Display name in docs and logs.                                              |
| `APP_VERSION`        | no                  | `0.1.0`                             | Version string returned by `/health`.                                       |
| `ENVIRONMENT`        | no                  | `dev`                               | `dev` or `prod`. `prod` disables docs, emits JSON logs, enforces secrets.   |
| `DEBUG`              | no                  | `true`                              | Verbose logging + SQL echo. Set `false` in production.                      |
| `DATABASE_URL`       | **yes (prod)**      | `sqlite+aiosqlite:///./portfolio.db`| Async DSN. Prod must use `postgresql+asyncpg://…`; SQLite is rejected.      |
| `CORS_ORIGINS`       | no                  | `http://localhost:3000`             | Comma-separated allowed frontend origins (no trailing slash).              |
| `TRUST_PROXY`        | no                  | `false`                             | Trust `X-Forwarded-For` for the client IP. Enable only behind a proxy.     |
| `ADMIN_TOKEN`        | **yes (prod)**      | *(empty)*                           | Bearer-style token for admin endpoints (sent as `X-Admin-Token`).          |
| `UPLOAD_DIR`         | no                  | `/data/uploads` (image)             | Where uploads are stored. Under Docker leave it unset — the volume is mounted there. |
| `MAX_UPLOAD_MB`      | no                  | `15`                                | Per-file upload ceiling, enforced while streaming.                         |
| `TELEGRAM_BOT_TOKEN` | no                  | *(empty)*                           | Enables Telegram contact notifications. Empty ⇒ notifications are skipped. |
| `TELEGRAM_CHAT_ID`   | no                  | *(empty)*                           | Chat/channel that receives notifications.                                  |
| `WEB_CONCURRENCY`    | no                  | `2`                                 | Gunicorn worker count (production entrypoint only).                        |
| `PORT`               | no                  | `8000`                              | Port the production server binds to.                                       |

In production the app **refuses to start** if `ADMIN_TOKEN` is empty or
`DATABASE_URL` still points at SQLite.

## Running tests

```bash
pytest          # integration + unit tests against in-memory SQLite
ruff check .    # lint
ruff format .   # format
```

Tests need no external services (they use an in-memory database and an in-process
ASGI client).

## API overview

| Method | Path                                    | Auth  | Description                         |
| ------ | --------------------------------------- | ----- | ---------------------------------- |
| GET    | `/health`                               | —     | Liveness probe.                    |
| GET    | `/api/v1/projects?lang=uz&limit=&offset=` | —   | List visible projects.             |
| GET    | `/api/v1/projects/{id}?lang=uz`         | —     | Get one project.                   |
| GET    | `/api/v1/media?type=photo&placement=gallery&lang=uz` | — | List visible media (both filters optional). |
| POST   | `/api/v1/contact`                       | —     | Submit a message (3/hour per IP).  |
| POST/PATCH/DELETE | `/api/v1/admin/projects[/{id}]` | admin | Manage projects.                   |
| GET    | `/api/v1/files/{filename}`              | —     | Serve an uploaded image.           |
| GET    | `/api/v1/admin/media`                   | admin | List every media item, hidden included. |
| POST   | `/api/v1/admin/media/upload`            | admin | Upload an image, returns its URL.  |
| POST/PATCH/DELETE | `/api/v1/admin/media[/{id}]`    | admin | Manage media.                      |
| GET    | `/api/v1/admin/contacts?unread_only=`   | admin | List contact messages.             |
| PATCH  | `/api/v1/admin/contacts/{id}/read`      | admin | Mark a message read.               |

A media item's `placement` decides where it appears: `hero` is the home-page
carousel, `gallery` (the default) is the media section. Both live in one table
because they are the same kind of asset, differing only in where they surface.

Uploads are stored by this service rather than a hosted image CDN, because the
usual providers refuse sign-ups from Uzbekistan. Only image extensions are
accepted, the stored filename is random (so a client filename can never steer a
write), and the size limit is enforced while streaming rather than trusting
`Content-Length`.

Deleting a media item deletes the file behind it, as does replacing its `url` —
but only after the transaction commits, and only for files this service stored
(a YouTube link or an external image is left alone). The inverse order would be
the unrecoverable one: a row pointing at a file that no longer exists. Debris
that escapes anyway is collected by `scripts/cleanup_orphans.py`.

Uploads are written to `UPLOAD_DIR`, which both images and compose files set to
`/data/uploads` — the path `docker-compose.prod.yml` mounts the `uploads_data`
volume over, and the dev compose binds to `./uploads`. **Do not set
`UPLOAD_DIR` in `.env`**: that overrides the mount and puts the images inside
the container, where the next `up --build` discards them while the database
keeps serving their URLs. In production the app logs a warning at startup when
the directory is not a mount point, which is how that mistake announces itself.

Admin requests send `X-Admin-Token: <ADMIN_TOKEN>`. Errors use one envelope:

```json
{ "error": { "code": "not_found", "message": "…", "detail": null } }
```

## Deploying to a Linux VPS

Everything runs on one machine through Docker Compose: Postgres, the API, and
the volume holding the uploaded images. These steps assume **Ubuntu 22.04** and
a domain name pointed at the server's public IP.

### 1. Open the ports

Some providers (Oracle Cloud among them) block traffic in two places — open
**both**:

1. **Provider firewall** (the cloud console's security list / security group):
   allow inbound TCP `80` and `443` from `0.0.0.0/0`.
2. **Host firewall** on the VM:

   ```bash
   sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save        # persist across reboots
   ```

### 2. Install Docker + Compose

```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER" && newgrp docker
```

### 3. Configure and start the app

```bash
git clone <your-repo-url> portfolio-backend && cd portfolio-backend
cp .env.example .env
# Edit .env:
#   ENVIRONMENT=prod
#   DEBUG=false
#   DATABASE_URL=postgresql+asyncpg://portfolio:STRONG_PASSWORD@db:5432/portfolio
#   POSTGRES_PASSWORD=STRONG_PASSWORD   # consumed by the db service
#   ADMIN_TOKEN=<a long random secret>
#   CORS_ORIGINS=https://your-portfolio.vercel.app
#   TRUST_PROXY=true                    # nginx sets X-Forwarded-For
#   (leave UPLOAD_DIR unset — the compose file mounts the uploads volume)
nano .env

docker compose -f docker-compose.prod.yml up -d --build
```

The API is now published on `127.0.0.1:8000` (localhost only). Migrations ran
automatically on startup.

Two named volumes now hold everything that must outlive a container:
`postgres_data` (the database) and `uploads_data` (the images). Re-running the
command above rebuilds the containers and leaves both untouched — that is what
makes a deploy safe to repeat.

### 4. nginx reverse proxy

```bash
sudo apt-get install -y nginx
sudo tee /etc/nginx/sites-available/portfolio >/dev/null <<'NGINX'
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX
sudo ln -s /etc/nginx/sites-available/portfolio /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Because nginx forwards `X-Forwarded-For`, keep `TRUST_PROXY=true` so rate
limiting sees the real client IP.

### 5. HTTPS with certbot

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.yourdomain.com
```

certbot edits the nginx config to serve HTTPS and sets up automatic renewal.
Verify: `curl https://api.yourdomain.com/health` → `{"status":"ok",...}`.

To deploy updates: `git pull && docker compose -f docker-compose.prod.yml up -d --build`.
The database and the uploaded images live in volumes, so they survive this.

### 6. Checking the images survive a deploy

Worth doing once, right after the first deploy — a broken volume is invisible
until the images are already gone:

```bash
# Upload something through the admin panel first, then:
docker compose -f docker-compose.prod.yml exec api ls -l /data/uploads
docker compose -f docker-compose.prod.yml up -d --build   # redeploy
docker compose -f docker-compose.prod.yml exec api ls -l /data/uploads
```

The same files must be listed both times, and the startup logs
(`docker compose -f docker-compose.prod.yml logs api`) must **not** contain the
"UPLOAD_DIR … is not a mount point" warning.

Both volumes belong in your backups:

```bash
docker compose -f docker-compose.prod.yml exec -T db \
    pg_dump -U portfolio portfolio > db-$(date +%F).sql
docker run --rm -v portfolio-backend_uploads_data:/data -v "$PWD:/out" \
    busybox tar czf /out/uploads-$(date +%F).tar.gz -C /data .
```

(The volume is prefixed with the compose project name — `docker volume ls`
shows the exact name on your machine.)

### 7. Clearing out orphaned uploads

Files with nothing pointing at them still appear over time: an image uploaded
into the admin form that was never saved, a deletion that failed, a row removed
by hand. `scripts/cleanup_orphans.py` finds them. It runs inside the container,
where both the database and the uploads are reachable:

```bash
# report only — deletes nothing
docker compose -f docker-compose.prod.yml exec api python scripts/cleanup_orphans.py

# actually remove them
docker compose -f docker-compose.prod.yml exec api python scripts/cleanup_orphans.py --delete
```

It considers media files, media cover images and project screenshots — hidden
rows included, which is why it reads the database rather than the API — and it
skips anything uploaded in the last hour (`--min-age-minutes`), so a file still
sitting in an unsaved admin form is never taken away.

## Connecting the frontend

Set `CORS_ORIGINS` to the exact origin(s) your static site is served from — no
trailing slash, scheme included. For a Vercel site plus local dev:

```
CORS_ORIGINS=https://your-portfolio.vercel.app,http://localhost:5173
```

Then the static site calls the API like this (default language is Uzbek):

```js
const API = "https://api.yourdomain.com/api/v1";

// List projects (Uzbek), first page.
const projects = await fetch(`${API}/projects?lang=uz&limit=20&offset=0`)
  .then((r) => r.json()); // -> { items: [...], total, limit, offset }

// One project in English.
const project = await fetch(`${API}/projects/1?lang=en`).then((r) => r.json());

// Photos only.
const photos = await fetch(`${API}/media?type=photo&lang=uz`).then((r) => r.json());

// Submit the contact form.
const res = await fetch(`${API}/contact`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    name: "Ali Valiyev",
    email: "ali@example.com",
    message: "Salom! Loyihangiz bo'yicha bog'lanmoqchiman.",
  }),
});
if (res.status === 201) {
  // { status: "sent" }
} else if (res.status === 429) {
  // rate limited — try again later
} else if (res.status === 422) {
  // validation error — inspect (await res.json()).error.detail
}
```

The API does not use cookies, so the frontend needs no `credentials` option. If
an origin is missing from `CORS_ORIGINS`, the browser blocks the response even
though the server processed it — this is the most common integration mistake.
