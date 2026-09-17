"""Persisting admin-uploaded images as two web-sized derivatives.

Third-party image hosts are the usual answer, but the two obvious ones refuse
sign-ups from Uzbekistan, so uploads are stored by the application itself.

What a phone produces is several megabytes and a few thousand pixels wide; what
a gallery tile needs is a fraction of that. Serving the original would make the
page unusable on mobile data, so nothing is stored as it arrived: every upload
is re-encoded into a ``thumb`` (grid tiles) and a ``large`` (full view), both
WebP. The original is discarded — it has no reader, and it is the one thing that
would keep the disk growing.

Re-encoding also drops the camera metadata, GPS coordinates included, which
would otherwise be published with the photo. Orientation is the exception: it is
read and *applied* first, so a portrait photo does not appear on its side.

The directory this writes to must be a mounted volume in production. A
container's own filesystem is thrown away on every deploy, which would silently
delete every uploaded image while leaving the database rows pointing at them.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import Settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)

# The public prefix every stored file is served under. A URL that does not start
# with it belongs to someone else (YouTube, an external CDN) and is never a path
# this service may touch.
PUBLIC_URL_PREFIX = "/api/v1/files/"

# What this service will serve. Everything it writes is WebP, except animated
# images, which keep their original format — hence the other entries.
ALLOWED_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

# What it will accept from a client. SVG is deliberately absent: it is a
# script-bearing document rather than a bitmap, and serving one from our own
# origin would let that script run there.
ACCEPTED_EXTENSIONS = frozenset(ALLOWED_EXTENSIONS)

# Target widths. 1600 covers a full-screen view on a laptop without carrying
# pixels no layout uses; 600 is twice the widest a grid tile gets, so it stays
# sharp on a high-density screen.
LARGE_WIDTH = 1600
THUMB_WIDTH = 600

# Quality is lower for the thumbnail: at tile size the difference is invisible,
# and it is the file every visitor downloads a dozen of.
LARGE_QUALITY = 80
THUMB_QUALITY = 72

# Read in chunks so a large upload never has to fit in memory all at once.
CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class StoredImage:
    """The two URLs one upload produces: what to show, and what to show first."""

    url: str
    thumbnail_url: str


class FileStorage:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @staticmethod
    def _extension(filename: str | None) -> str:
        suffix = Path(filename or "").suffix.lower()
        if suffix not in ACCEPTED_EXTENSIONS:
            allowed = ", ".join(sorted(ACCEPTED_EXTENSIONS))
            raise ValidationError(
                f"Unsupported file type '{suffix or 'unknown'}'. Allowed: {allowed}."
            )
        return suffix

    async def save(self, upload: UploadFile) -> StoredImage:
        """Store ``upload`` as two derivatives and return their public URLs.

        Stored names are random rather than derived from the client's filename:
        that removes any path-traversal question entirely, and means two uploads
        called "photo.jpg" cannot overwrite one another.
        """
        extension = self._extension(upload.filename)
        data = await self._read_within_limit(upload)
        name = secrets.token_urlsafe(16)

        with self._decode(data) as image:
            # An animated GIF re-encoded frame by frame is a good way to produce
            # a subtly broken animation. They are rare and already small, so
            # they are stored exactly as they arrived.
            if self._frame_count(image) > 1:
                url = self._url_of(self._write_bytes(f"{name}{extension}", data))
                return StoredImage(url=url, thumbnail_url=url)

            upright = self._upright(image)
            written: list[Path] = []
            try:
                large = self._write_webp(
                    upright, f"{name}.webp", LARGE_WIDTH, LARGE_QUALITY
                )
                written.append(large)
                thumb = self._write_webp(
                    upright, f"{name}_thumb.webp", THUMB_WIDTH, THUMB_QUALITY
                )
            except Exception:
                # A half-finished upload must not leave files behind — nothing
                # references them, so no one would clean them up by hand.
                for path in written:
                    path.unlink(missing_ok=True)
                raise

        return StoredImage(url=self._url_of(large), thumbnail_url=self._url_of(thumb))

    @staticmethod
    def _decode(data: bytes) -> Image.Image:
        """Open the upload, refusing anything that is not a readable image.

        Decoding failures are the client's problem, not the server's: the
        extension is only a claim, and a truncated or mislabelled file must come
        back as a validation error rather than a 500. Write failures further
        down are deliberately *not* caught here — those really are ours.
        """
        try:
            return Image.open(BytesIO(data))
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValidationError(
                "That file is not a readable image. Upload a jpg, png, webp or gif."
            ) from exc

    @staticmethod
    def _frame_count(image: Image.Image) -> int:
        try:
            return int(getattr(image, "n_frames", 1))
        except OSError:  # a damaged sequence; treat it as a single frame
            return 1

    @staticmethod
    def _upright(image: Image.Image) -> Image.Image:
        """Apply the EXIF orientation. This is where truncated data surfaces."""
        try:
            return ImageOps.exif_transpose(image)
        except OSError as exc:
            raise ValidationError(
                "That image could not be read — it looks damaged or incomplete."
            ) from exc

    def make_thumbnail(self, url: str | None) -> str | None:
        """Derive a thumbnail for an image that was stored without one.

        Exists for the backfill script: rows created before the pipeline made
        two sizes still point at one large file, and a gallery of those is the
        slow page this whole change is about. Returns the new URL, or ``None``
        when there is nothing to derive from.
        """
        if not self.owns(url):
            return None

        source = self._settings.upload_path / Path(str(url)).name
        if not source.is_file():
            return None

        with self._decode(source.read_bytes()) as image:
            if self._frame_count(image) > 1:
                return None  # animated: the original is the only version
            thumb = self._write_webp(
                self._upright(image),
                f"{source.stem}_thumb.webp",
                THUMB_WIDTH,
                THUMB_QUALITY,
            )
        return self._url_of(thumb)

    async def _read_within_limit(self, upload: UploadFile) -> bytes:
        """Read the upload into memory, refusing anything over the limit.

        The ceiling is enforced while streaming rather than from
        ``Content-Length``: the header is client-supplied and may simply be a
        lie. Buffering is fine at this size, and Pillow needs the whole image
        anyway.
        """
        chunks: list[bytes] = []
        size = 0
        try:
            while chunk := await upload.read(CHUNK_BYTES):
                size += len(chunk)
                if size > self._settings.max_upload_bytes:
                    raise ValidationError(
                        f"File is larger than {self._settings.MAX_UPLOAD_MB} MB."
                    )
                chunks.append(chunk)
        finally:
            await upload.close()

        if size == 0:
            raise ValidationError("The uploaded file is empty.")
        return b"".join(chunks)

    def _write_webp(
        self, image: Image.Image, filename: str, width: int, quality: int
    ) -> Path:
        """Write ``image`` as WebP, no wider than ``width``.

        A smaller original is left at its own size: upscaling invents detail and
        costs bytes for a picture that only looks softer.
        """
        if image.width > width:
            height = round(image.height * width / image.width)
            image = image.resize((width, height), Image.Resampling.LANCZOS)

        path = self._settings.upload_path / filename
        # No `exif=` argument, so the camera metadata (GPS included) is dropped
        # rather than copied into the file the site publishes.
        self._drop_unsupported_modes(image).save(
            path, "WEBP", quality=quality, method=6
        )
        return path

    @staticmethod
    def _drop_unsupported_modes(image: Image.Image) -> Image.Image:
        """Convert to a mode WebP can store, keeping transparency where it exists."""
        transparent = image.mode in ("RGBA", "LA") or (
            image.mode == "P" and "transparency" in image.info
        )
        return image.convert("RGBA" if transparent else "RGB")

    def _write_bytes(self, filename: str, data: bytes) -> Path:
        path = self._settings.upload_path / filename
        path.write_bytes(data)
        return path

    @staticmethod
    def _url_of(path: Path) -> str:
        return f"{PUBLIC_URL_PREFIX}{path.name}"

    @staticmethod
    def owns(url: str | None) -> bool:
        """Whether ``url`` points at a file this service stored.

        The single gate for every deletion: a media item may just as well hold a
        YouTube link or an external image, and deleting is irreversible, so the
        question is answered in one place rather than at each call site. The
        remainder after the prefix must be a bare filename with a known image
        extension — a nested path or an unknown suffix is not something we wrote.
        """
        if not url or not url.startswith(PUBLIC_URL_PREFIX):
            return False

        name = url[len(PUBLIC_URL_PREFIX) :]
        return (
            bool(name)
            and name == Path(name).name
            and Path(name).suffix.lower() in ALLOWED_EXTENSIONS
        )

    def delete(self, url: str | None) -> bool:
        """Remove a previously stored file. Returns whether anything was deleted.

        Never raises: this runs after the response has been sent, where an
        exception could no longer be reported to anyone, and a file that failed
        to disappear is debris the cleanup script can collect later.
        """
        if not self.owns(url):
            return False

        target = self._settings.upload_path / Path(str(url)).name
        try:
            if not target.is_file():
                # Already gone — deleted by hand, or by a retried request.
                return False
            target.unlink()
        except OSError as exc:
            logger.warning("Could not delete uploaded file %s: %s", target, exc)
            return False

        logger.info("Deleted uploaded file %s", target.name)
        return True
