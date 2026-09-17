"""Uploads are re-encoded, not stored as they arrive.

What matters here is what reaches a visitor's phone: the number of bytes, and
what is embedded in them. A photo straight from a camera is several megabytes
and carries the coordinates of wherever it was taken, so the pipeline shrinks
it, converts it, and strips the metadata — while applying the one EXIF field
that must not be thrown away, orientation.
"""

from __future__ import annotations

from io import BytesIO

import httpx
import pytest
from PIL import Image

from app.core.config import get_settings
from app.services.storage import FileStorage
from tests.conftest import ADMIN_HEADERS, make_image, upload_files

UPLOAD_URL = "/api/v1/admin/media/upload"


def make_animated_gif() -> bytes:
    buffer = BytesIO()
    # Distinct colours per frame: identical frames are collapsed into one by the
    # GIF writer, which would leave the file with nothing to animate.
    frames = [Image.new("RGB", (40, 40), c).convert("P") for c in ("red", "green", "blue")]
    frames[0].save(buffer, "GIF", save_all=True, append_images=frames[1:], duration=80)
    return buffer.getvalue()


async def upload(
    client: httpx.AsyncClient, data: bytes, name: str = "photo.jpg"
) -> dict:
    response = await client.post(
        UPLOAD_URL, headers=ADMIN_HEADERS, files=upload_files(name, data)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def fetch_image(client: httpx.AsyncClient, url: str) -> Image.Image:
    response = await client.get(url)
    assert response.status_code == 200
    return Image.open(BytesIO(response.content))


async def test_upload_returns_two_servable_webp_urls(client: httpx.AsyncClient) -> None:
    body = await upload(client, make_image(2400, 1600))

    assert body["url"].endswith(".webp")
    assert body["thumbnail_url"].endswith(".webp")
    assert body["url"] != body["thumbnail_url"]
    # The stored names must not echo the client's, or two uploads called
    # "photo.jpg" would collide.
    assert "photo" not in body["url"]

    for url in (body["url"], body["thumbnail_url"]):
        served = await client.get(url)
        assert served.status_code == 200
        assert served.headers["content-type"] == "image/webp"


async def test_a_large_photo_is_resized_to_both_target_widths(
    client: httpx.AsyncClient,
) -> None:
    body = await upload(client, make_image(3000, 2000))

    large = await fetch_image(client, body["url"])
    thumb = await fetch_image(client, body["thumbnail_url"])

    assert large.size == (1600, 1067)  # aspect ratio preserved
    assert thumb.size == (600, 400)


async def test_the_stored_files_are_a_fraction_of_the_original(
    client: httpx.AsyncClient,
) -> None:
    """The whole point: what the gallery downloads is much smaller."""
    original = make_image(3000, 2000)
    body = await upload(client, original)

    upload_dir = get_settings().upload_path
    thumb_bytes = (upload_dir / body["thumbnail_url"].rsplit("/", 1)[-1]).stat().st_size

    assert thumb_bytes < len(original) / 4


async def test_a_small_image_is_not_upscaled(client: httpx.AsyncClient) -> None:
    """Upscaling invents detail and costs bytes for a picture that looks softer."""
    body = await upload(client, make_image(120, 90))

    large = await fetch_image(client, body["url"])
    thumb = await fetch_image(client, body["thumbnail_url"])

    assert large.size == (120, 90)
    assert thumb.size == (120, 90)


async def test_camera_metadata_is_not_published(client: httpx.AsyncClient) -> None:
    """A photo carries where it was taken; the site must not hand that out."""
    exif = Image.Exif()
    exif[0x010F] = "TestCam"  # Make
    exif[0x0110] = "Model X"  # Model
    exif.get_ifd(0x8825)[1] = "N"  # GPSLatitudeRef

    original = make_image(800, 600, exif=exif)
    # Sanity: the upload really does arrive carrying all of that.
    assert dict(Image.open(BytesIO(original)).getexif())

    body = await upload(client, original)

    large = await fetch_image(client, body["url"])
    assert dict(large.getexif()) == {}


async def test_orientation_is_applied_rather_than_stored(
    client: httpx.AsyncClient,
) -> None:
    """Orientation is the one EXIF field that must survive — as pixels."""
    exif = Image.Exif()
    exif[0x0112] = 6  # "rotate 90° clockwise when displaying"

    body = await upload(client, make_image(200, 100, exif=exif))

    large = await fetch_image(client, body["url"])
    # Rotated during encoding, so a viewer that ignores EXIF still sees it right.
    assert large.size == (100, 200)


async def test_transparency_survives_the_conversion(client: httpx.AsyncClient) -> None:
    body = await upload(
        client, make_image(300, 300, fmt="PNG", mode="RGBA"), name="logo.png"
    )

    large = await fetch_image(client, body["url"])
    assert large.mode in ("RGBA", "RGBa")


async def test_an_animated_gif_is_stored_untouched(client: httpx.AsyncClient) -> None:
    """Re-encoding frame by frame is a good way to break an animation."""
    original = make_animated_gif()
    body = await upload(client, original, name="loop.gif")

    assert body["url"].endswith(".gif")
    # One file, referenced twice: there is no smaller version to point at.
    assert body["url"] == body["thumbnail_url"]

    served = await client.get(body["url"])
    assert served.content == original


async def test_svg_uploads_are_refused(client: httpx.AsyncClient) -> None:
    """An SVG is a script-bearing document, not a bitmap."""
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'

    response = await client.post(
        UPLOAD_URL, headers=ADMIN_HEADERS, files=upload_files("x.svg", svg, "image/svg+xml")
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_a_file_that_is_not_an_image_is_refused_without_debris(
    client: httpx.AsyncClient,
) -> None:
    """The extension is a claim; decoding is what checks it."""
    settings = get_settings()
    before = set(settings.upload_path.iterdir())

    response = await client.post(
        UPLOAD_URL,
        headers=ADMIN_HEADERS,
        files=upload_files("fake.png", b"this is not an image", "image/png"),
    )

    assert response.status_code == 422
    assert set(settings.upload_path.iterdir()) == before


@pytest.mark.parametrize("filename", ["script.py", "archive.zip", "noextension"])
async def test_non_image_extensions_are_refused(
    client: httpx.AsyncClient, filename: str
) -> None:
    response = await client.post(
        UPLOAD_URL, headers=ADMIN_HEADERS, files=upload_files(filename, b"whatever")
    )
    assert response.status_code == 422


async def test_a_thumbnail_can_be_derived_afterwards(
    client: httpx.AsyncClient,
) -> None:
    """What the backfill script does for rows stored before the pipeline existed."""
    body = await upload(client, make_image(2000, 1000))
    storage = FileStorage(get_settings())
    # Pretend only the large file was ever written.
    (get_settings().upload_path / body["thumbnail_url"].rsplit("/", 1)[-1]).unlink()

    derived = storage.make_thumbnail(body["url"])

    assert derived is not None
    thumb = await fetch_image(client, derived)
    assert thumb.size == (600, 300)


async def test_no_thumbnail_is_derived_for_an_external_link() -> None:
    storage = FileStorage(get_settings())

    assert storage.make_thumbnail("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is None


async def test_deleting_the_media_item_removes_both_derivatives(
    client: httpx.AsyncClient,
) -> None:
    body = await upload(client, make_image(1200, 900))
    created = await client.post(
        "/api/v1/admin/media",
        headers=ADMIN_HEADERS,
        json={"media_type": "photo", **body},
    )
    assert created.status_code == 201

    response = await client.delete(
        f"/api/v1/admin/media/{created.json()['id']}", headers=ADMIN_HEADERS
    )

    assert response.status_code == 204
    upload_dir = get_settings().upload_path
    for url in (body["url"], body["thumbnail_url"]):
        assert not (upload_dir / url.rsplit("/", 1)[-1]).exists()
