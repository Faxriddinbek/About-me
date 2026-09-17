"""Persisting admin-uploaded files to disk.

Third-party image hosts are the usual answer, but the two obvious ones refuse
sign-ups from Uzbekistan, so uploads are stored by the application itself.

The directory this writes to must be a mounted volume in production. A
container's own filesystem is thrown away on every deploy, which would silently
delete every uploaded image while leaving the database rows pointing at them.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import UploadFile

from app.core.config import Settings
from app.core.exceptions import ValidationError

# Only formats a browser renders natively. Whitelisting extensions (rather than
# trusting the client's Content-Type, which is trivially spoofed) is what keeps
# the directory from becoming a place to park executables.
ALLOWED_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".avif": "image/avif",
    ".svg": "image/svg+xml",
}

# Read in chunks so a large upload never has to fit in memory all at once.
CHUNK_BYTES = 1024 * 1024


class FileStorage:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @staticmethod
    def _extension(filename: str | None) -> str:
        suffix = Path(filename or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
            raise ValidationError(
                f"Unsupported file type '{suffix or 'unknown'}'. Allowed: {allowed}."
            )
        return suffix

    async def save(self, upload: UploadFile) -> str:
        """Write ``upload`` to disk and return the public URL path.

        The stored name is random rather than derived from the client's
        filename: that removes any path-traversal question entirely, and means
        two uploads called "photo.jpg" cannot overwrite one another.
        """
        extension = self._extension(upload.filename)
        name = f"{secrets.token_urlsafe(16)}{extension}"
        destination = self._settings.upload_path / name

        limit = self._settings.max_upload_bytes
        written = 0

        try:
            with destination.open("wb") as handle:
                while chunk := await upload.read(CHUNK_BYTES):
                    written += len(chunk)
                    # Enforced while streaming, not from Content-Length: the
                    # header is client-supplied and may simply be a lie.
                    if written > limit:
                        raise ValidationError(
                            f"File is larger than {self._settings.MAX_UPLOAD_MB} MB."
                        )
                    handle.write(chunk)
        except Exception:
            # A rejected or failed upload must not leave a partial file behind.
            destination.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

        if written == 0:
            destination.unlink(missing_ok=True)
            raise ValidationError("The uploaded file is empty.")

        return f"/api/v1/files/{name}"

    def delete(self, url: str) -> bool:
        """Remove a previously stored file. Returns whether anything was deleted.

        Only the final path segment is used, so a crafted URL cannot reach
        outside the upload directory.
        """
        name = Path(url).name
        if not name:
            return False

        target = self._settings.upload_path / name
        if not target.is_file():
            return False

        target.unlink()
        return True
