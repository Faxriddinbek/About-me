# syntax=docker/dockerfile:1

# --- Builder: install dependencies into a self-contained virtualenv ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# build-essential lets any package without a prebuilt wheel compile from source.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# --- Runtime: copy only the venv + app code, run as an unprivileged user ------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

# Non-root system user; the app never needs root at runtime.
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . .

# WORKDIR created /app as root; give it to the app user so the process can write
# there (e.g. the SQLite fallback file when no Postgres DATABASE_URL is set).
RUN chmod +x /app/start.sh && chown app:app /app

# Uploads live outside /app, on a directory the compose file mounts a volume
# over. Creating it here — owned by the app user — is what makes that work:
# Docker seeds an empty named volume from the image, ownership included, so the
# non-root process finds a writable directory instead of a root-owned mount.
RUN mkdir -p /data/uploads && chown -R app:app /data

# Default to the mounted path, so a deployment that forgets to set UPLOAD_DIR
# still writes somewhere persistent rather than into the container's own layer.
ENV UPLOAD_DIR=/data/uploads

USER app

EXPOSE 8000

# Mark the container unhealthy if /health stops returning 200. Uses stdlib only
# (the slim image has no curl).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["/app/start.sh"]
