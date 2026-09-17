"""Serving admin-uploaded files.

A route rather than a ``StaticFiles`` mount so the filename can be validated
before it ever reaches the filesystem, and so responses carry an explicit
long-lived cache header — stored names are random and never reused, which makes
the content at a given URL immutable by construction.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse

from app.api.deps import SettingsDep
from app.core.exceptions import NotFoundError
from app.services.storage import ALLOWED_EXTENSIONS

router = APIRouter(prefix="/files", tags=["files"])

CACHE_CONTROL = "public, max-age=31536000, immutable"


@router.get(
    "/{filename}",
    response_class=FileResponse,
    summary="Serve an uploaded file",
    description="Return a previously uploaded image. Responds 404 if it is gone.",
)
async def get_file(filename: str, settings: SettingsDep) -> Response:
    # Reduce to the bare name: even though the path parameter cannot contain a
    # slash, this makes the traversal guarantee independent of routing details.
    name = Path(filename).name
    suffix = Path(name).suffix.lower()

    if name != filename or suffix not in ALLOWED_EXTENSIONS:
        raise NotFoundError("File not found.")

    path = settings.upload_path / name
    if not path.is_file():
        raise NotFoundError("File not found.")

    return FileResponse(
        path,
        media_type=ALLOWED_EXTENSIONS[suffix],
        headers={"Cache-Control": CACHE_CONTROL},
    )
