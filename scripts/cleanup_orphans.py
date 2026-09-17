"""Report (and optionally delete) uploaded files that no database row refers to.

Deleting a media item now takes its file with it, but debris still accumulates:
an image uploaded in the admin form that was never saved, a file whose deletion
failed, or rows removed straight from the database. This script finds those.

It reads the database directly rather than going through the API, because the
public endpoints only return *visible* rows — a hidden project's screenshot
would look unreferenced and be deleted. It also has to run where the uploads
actually live, which is the same place the database is reachable from::

    # on the server, inside the API container
    docker compose -f docker-compose.prod.yml exec api python scripts/cleanup_orphans.py
    docker compose -f docker-compose.prod.yml exec api python scripts/cleanup_orphans.py --delete

Without ``--delete`` nothing is removed: it prints what it would do and stops.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Allow `python scripts/cleanup_orphans.py` from the project root: without this
# sys.path[0] is scripts/, and `import app` would fail.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import (  # noqa: E402
    async_session_factory,
    dispose_engine,
    engine,
)
from app.models import MediaItem, Project  # noqa: E402
from app.services.storage import FileStorage  # noqa: E402

# A file uploaded minutes ago may simply be sitting in an admin form that has
# not been saved yet. Anything younger than this is left alone, so a cleanup
# running at the wrong moment cannot delete work in progress.
DEFAULT_MIN_AGE_MINUTES = 60


async def referenced_filenames() -> set[str]:
    """Every stored filename that some row still points at.

    Covers all three URL-bearing columns — a media item's file and its cover
    image, and a project's screenshot — and ignores external links.
    """
    names: set[str] = set()

    async with async_session_factory() as session:
        media = await session.execute(select(MediaItem.url, MediaItem.thumbnail_url))
        projects = await session.execute(select(Project.image_url))

        urls = [url for row in media.all() for url in row]
        urls += [row[0] for row in projects.all()]

    for url in urls:
        if FileStorage.owns(url):
            names.add(Path(str(url)).name)
    return names


def select_orphans(
    files: list[Path], referenced: set[str], *, cutoff: float
) -> list[Path]:
    """Files that nothing refers to and that are older than ``cutoff``.

    Kept free of I/O beyond the stat call so the rule itself can be tested
    without a database or a real upload directory.
    """
    orphans = []
    for path in sorted(files):
        if path.name in referenced or path.name.startswith("."):
            continue
        if path.stat().st_mtime > cutoff:
            continue
        orphans.append(path)
    return orphans


def human_size(total_bytes: int) -> str:
    megabytes = total_bytes / (1024 * 1024)
    return f"{megabytes:.1f} MB" if megabytes >= 0.1 else f"{total_bytes} B"


async def run(*, delete: bool, min_age_minutes: int) -> int:
    # With DEBUG on the engine echoes every statement, which would bury the
    # report this script exists to print. Raising the log level does not help:
    # `echo` sets its own level on a per-engine logger. Turning the flag off is
    # what actually silences it.
    engine.echo = False

    settings = get_settings()
    upload_dir = settings.upload_path

    try:
        referenced = await referenced_filenames()
    finally:
        await dispose_engine()

    files = [path for path in upload_dir.iterdir() if path.is_file()]
    cutoff = time.time() - min_age_minutes * 60
    orphans = select_orphans(files, referenced, cutoff=cutoff)

    print(f"Upload directory : {upload_dir}")
    print(f"Files on disk    : {len(files)}")
    print(f"Referenced       : {len(referenced)}")
    print(f"Orphaned         : {len(orphans)} (older than {min_age_minutes} min)\n")

    if not orphans:
        print("Nothing to clean up.")
        return 0

    reclaimed = 0
    for path in orphans:
        size = path.stat().st_size
        reclaimed += size
        if delete:
            try:
                path.unlink()
                print(f"  deleted  {path.name}  ({human_size(size)})")
            except OSError as exc:
                print(f"  FAILED   {path.name}: {exc}", file=sys.stderr)
                reclaimed -= size
        else:
            print(f"  would delete  {path.name}  ({human_size(size)})")

    verb = "Reclaimed" if delete else "Would reclaim"
    print(f"\n{verb} {human_size(reclaimed)}.")
    if not delete:
        print("Nothing was deleted. Re-run with --delete to remove these files.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete the orphans (default: only report them).",
    )
    parser.add_argument(
        "--min-age-minutes",
        type=int,
        default=DEFAULT_MIN_AGE_MINUTES,
        help=(
            "Ignore files younger than this, which may still belong to an "
            f"unsaved admin form (default: {DEFAULT_MIN_AGE_MINUTES})."
        ),
    )
    args = parser.parse_args()
    return asyncio.run(
        run(delete=args.delete, min_age_minutes=args.min_age_minutes)
    )


if __name__ == "__main__":
    raise SystemExit(main())
