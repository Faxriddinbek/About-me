"""Populate a running API with the content in ``seed_data.json``.

Production hides ``/docs``, so there is no interactive form to paste content
into. This script is the supported way to load real data into any environment:
it talks to the same public admin endpoints an operator would, over HTTP, using
only the standard library — no virtualenv, no database access, nothing to
install.

Usage::

    # local (docker compose up -d first)
    python scripts/seed.py

    # production
    python scripts/seed.py --base-url https://api.example.com --token "$ADMIN_TOKEN"

Seeding is idempotent by title: an existing project or media item with the same
title is updated rather than duplicated, so the script is safe to re-run after
editing ``seed_data.json``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).with_name("seed_data.json")

DEFAULT_BASE_URL = "http://localhost:8001"
DEFAULT_TOKEN = "dev-admin-token"  # matches docker-compose.yml's dev value


class ApiError(RuntimeError):
    """An API call returned a non-2xx status."""


def call(
    method: str, url: str, token: str, payload: dict[str, Any] | None = None
) -> Any:
    """Issue one JSON request and return the decoded body (``None`` for 204)."""
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Content-Type", "application/json")
    request.add_header("X-Admin-Token", token)

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise ApiError(f"{method} {url} -> {exc.code}\n{detail}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(f"Cannot reach {url}: {exc.reason}") from exc


# How to recognise "the same item" on a re-run, per kind. Projects are keyed by
# their Uzbek title (a NOT NULL column, resolved into `title` by the public API);
# media titles are optional, so their URL is the only reliable identity.
IDENTITY = {
    "projects": ("title", "title_uz"),
    "media": ("url", "url"),
}


def upsert(
    kind: str, entries: list[dict[str, Any]], base_url: str, token: str
) -> None:
    """Create or update every entry of one kind ("projects" or "media").

    The admin routes are write-only, so existing rows are discovered through the
    public listing. That only returns visible items — which is exactly what this
    file seeds, so nothing is missed.
    """
    response_key, entry_key = IDENTITY[kind]

    # limit=100 is the API's maximum, far beyond any realistic portfolio size.
    existing = call("GET", f"{base_url}/api/v1/{kind}?lang=uz&limit=100", token)
    by_identity = {
        item[response_key]: item["id"]
        for item in existing.get("items", [])
        if item.get(response_key)
    }

    for entry in entries:
        identity = entry.get(entry_key)
        existing_id = by_identity.get(identity)

        if existing_id is None:
            call("POST", f"{base_url}/api/v1/admin/{kind}", token, entry)
            print(f"  + created  {identity}")
        else:
            call("PATCH", f"{base_url}/api/v1/admin/{kind}/{existing_id}", token, entry)
            print(f"  ~ updated  {identity}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SEED_BASE_URL", DEFAULT_BASE_URL),
        help=f"API root (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("ADMIN_TOKEN", DEFAULT_TOKEN),
        help="Value for the X-Admin-Token header",
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    try:
        health = call("GET", f"{base_url}/health", args.token)
        print(f"Connected to {base_url} (version {health.get('version')})\n")

        print("Projects:")
        upsert("projects", data.get("projects", []), base_url, args.token)
        print("\nMedia:")
        upsert("media", data.get("media", []), base_url, args.token)
    except ApiError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
