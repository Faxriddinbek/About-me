"""Upload and file-serving endpoints.

These are the only routes that touch the filesystem, so the tests concentrate on
what could go wrong there: writing something that should not be written, reading
something outside the upload directory, and leaving debris behind after a
rejected upload.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import get_settings
from tests.conftest import ADMIN_HEADERS, make_image, upload_files

UPLOAD_URL = "/api/v1/admin/media/upload"


async def test_upload_returns_a_servable_url(client: httpx.AsyncClient) -> None:
    response = await client.post(
        UPLOAD_URL, headers=ADMIN_HEADERS, files=upload_files("photo.jpg", make_image())
    )
    assert response.status_code == 201

    url = response.json()["url"]
    assert url.startswith("/api/v1/files/")
    # The stored name must not echo the client's, or two uploads called
    # "photo.jpg" would collide.
    assert "photo" not in url

    served = await client.get(url)
    assert served.status_code == 200
    # Whatever arrives is re-encoded; see tests/test_image_processing.py.
    assert served.headers["content-type"] == "image/webp"


async def test_upload_requires_admin_token(client: httpx.AsyncClient) -> None:
    response = await client.post(
        UPLOAD_URL, files=upload_files("photo.jpg", make_image())
    )
    assert response.status_code == 401


@pytest.mark.parametrize("filename", ["script.py", "archive.zip", "noextension"])
async def test_upload_rejects_non_image_extensions(
    client: httpx.AsyncClient, filename: str
) -> None:
    response = await client.post(
        UPLOAD_URL, headers=ADMIN_HEADERS, files=upload_files(filename, b"whatever")
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_upload_rejects_a_file_over_the_limit_without_leaving_debris(
    client: httpx.AsyncClient,
) -> None:
    settings = get_settings()
    before = set(settings.upload_path.iterdir())

    oversized = b"\x00" * (settings.max_upload_bytes + 1024)
    response = await client.post(
        UPLOAD_URL, headers=ADMIN_HEADERS, files=upload_files("big.png", oversized)
    )

    assert response.status_code == 422
    # The limit is enforced while reading, before anything is written, so a
    # rejected upload leaves the directory exactly as it found it.
    assert set(settings.upload_path.iterdir()) == before


async def test_upload_rejects_an_empty_file(client: httpx.AsyncClient) -> None:
    response = await client.post(
        UPLOAD_URL, headers=ADMIN_HEADERS, files=upload_files("empty.png", b"")
    )
    assert response.status_code == 422


async def test_serving_an_unknown_file_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/files/does-not-exist.png")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "attempt",
    [
        "..%2f..%2fapp%2fmain.py",  # encoded traversal
        "%2e%2e%2f.env",
        "settings.py",  # right directory, wrong kind of file
    ],
)
async def test_serving_refuses_paths_outside_the_upload_directory(
    client: httpx.AsyncClient, attempt: str
) -> None:
    response = await client.get(f"/api/v1/files/{attempt}")
    assert response.status_code == 404
