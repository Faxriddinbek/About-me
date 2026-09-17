"""Give older media items the thumbnail the upload pipeline now makes for them.

Uploads used to be stored as a single file, so a gallery of them downloads the
full-size image per tile. This walks the media table, derives a thumbnail for
every row that is still missing one, and records it.

Like the cleanup script it talks to the database directly and must run where the
uploads live::

    docker compose -f docker-compose.prod.yml exec api python scripts/backfill_thumbnails.py
    docker compose -f docker-compose.prod.yml exec api python scripts/backfill_thumbnails.py --apply

Without ``--apply`` nothing is written: it reports what it would do and stops.
Re-running it is safe — rows that already have a thumbnail are skipped.

Project screenshots are left alone: a project card shows one image and has no
column to store a second size in.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow `python scripts/backfill_thumbnails.py` from the project root: without
# this sys.path[0] is scripts/, and `import app` would fail.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.exceptions import AppError  # noqa: E402
from app.db.session import (  # noqa: E402
    async_session_factory,
    dispose_engine,
    engine,
)
from app.models import MediaItem  # noqa: E402
from app.services.storage import FileStorage  # noqa: E402


async def run(*, apply: bool) -> int:
    # With DEBUG on the engine echoes every statement, which would bury the
    # report this script exists to print. Raising the log level does not help:
    # `echo` sets its own level on a per-engine logger. Turning the flag off is
    # what actually silences it.
    engine.echo = False

    storage = FileStorage(get_settings())
    made = skipped = failed = 0

    try:
        async with async_session_factory() as session:
            rows = (await session.execute(select(MediaItem))).scalars().all()

            for row in rows:
                if row.thumbnail_url or not storage.owns(row.url):
                    continue  # already done, or an external link

                try:
                    thumbnail = storage.make_thumbnail(row.url)
                except AppError as exc:
                    print(f"  FAILED  #{row.id}: {exc.message}", file=sys.stderr)
                    failed += 1
                    continue

                if thumbnail is None:
                    print(f"  skipped #{row.id}: {row.url} (missing or animated)")
                    skipped += 1
                    continue

                made += 1
                if apply:
                    row.thumbnail_url = thumbnail
                    print(f"  made    #{row.id}  ->  {thumbnail}")
                else:
                    # The file was written; without --apply the row is not
                    # updated, so cleanup_orphans.py will collect it later.
                    print(f"  would make  #{row.id}  ->  {thumbnail}")

            if apply:
                await session.commit()
    finally:
        await dispose_engine()

    print(
        f"\nMedia items: {len(rows)} | thumbnails "
        f"{'created' if apply else 'that would be created'}: {made} | "
        f"skipped: {skipped} | failed: {failed}"
    )
    if not apply and made:
        print("Nothing was recorded. Re-run with --apply to keep these thumbnails.")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Record the thumbnails (default: report only).",
    )
    args = parser.parse_args()
    return asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
