"""Videos are uploaded to and served from our own storage.

They are stored unchanged, so what matters is the gatekeeping around them: the
size ceiling, the container-format check, the free-space margin, no half-written
files left behind — and that the browser can seek (HTTP Range).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.core.config import get_settings
from app.services.storage import FileStorage
from tests.conftest import ADMIN_HEADERS, upload_files

ADMIN_MEDIA = "/api/v1/admin/media"
UPLOAD_URL = f"{ADMIN_MEDIA}/upload"

# A minimal ISO-BMFF header ("ftyp" box) followed by filler, enough for the
# signature check; the server never decodes the video itself.
MP4_BYTES = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"\x00" * 4096
WEBM_BYTES = b"\x1a\x45\xdf\xa3" + b"\x00" * 4096


def _path_of(url: str) -> Path:
    return get_settings().upload_path / Path(url).name


def _leftovers() -> list[Path]:
    return list(get_settings().upload_path.glob(".*.part"))


async def _upload(client: httpx.AsyncClient, name: str, data: bytes, ctype: str) -> httpx.Response:
    return await client.post(
        UPLOAD_URL, headers=ADMIN_HEADERS, files=upload_files(name, data, ctype)
    )


async def test_mp4_is_stored_unchanged(client: httpx.AsyncClient) -> None:
    response = await _upload(client, "clip.mp4", MP4_BYTES, "video/mp4")

    assert response.status_code == 201
    body = response.json()
    assert body["media_type"] == "video"
    assert body["thumbnail_url"] is None
    assert body["url"].endswith(".mp4")
    assert _path_of(body["url"]).read_bytes() == MP4_BYTES


async def test_webm_is_accepted(client: httpx.AsyncClient) -> None:
    response = await _upload(client, "clip.webm", WEBM_BYTES, "video/webm")
    assert response.status_code == 201
    assert response.json()["url"].endswith(".webm")


async def test_video_is_served_with_range_support(client: httpx.AsyncClient) -> None:
    url = (await _upload(client, "clip.mp4", MP4_BYTES, "video/mp4")).json()["url"]

    full = await client.get(url)
    assert full.status_code == 200
    assert full.headers["content-type"] == "video/mp4"
    assert full.headers.get("accept-ranges") == "bytes"

    partial = await client.get(url, headers={"Range": "bytes=0-99"})
    assert partial.status_code == 206
    assert partial.content == MP4_BYTES[:100]


async def test_renamed_non_video_is_rejected(client: httpx.AsyncClient) -> None:
    response = await _upload(client, "evil.mp4", b"<html><script>x</script></html>", "video/mp4")

    assert response.status_code == 422
    assert not _leftovers()


async def test_oversized_video_is_rejected_and_cleaned_up(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "MAX_VIDEO_UPLOAD_MB", 0)
    before = set(settings.upload_path.iterdir())

    response = await _upload(client, "big.mp4", MP4_BYTES, "video/mp4")

    assert response.status_code == 422
    assert "larger than" in response.json()["error"]["message"]
    assert set(settings.upload_path.iterdir()) == before


async def test_upload_refused_when_disk_is_nearly_full(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "MIN_FREE_DISK_MB", 10**9)  # ~1 PB margin

    response = await _upload(client, "clip.mp4", MP4_BYTES, "video/mp4")

    assert response.status_code == 422
    assert "disk space" in response.json()["error"]["message"]


async def test_deleting_video_media_deletes_the_file(client: httpx.AsyncClient) -> None:
    url = (await _upload(client, "clip.mp4", MP4_BYTES, "video/mp4")).json()["url"]
    created = await client.post(
        ADMIN_MEDIA, headers=ADMIN_HEADERS, json={"media_type": "video", "url": url}
    )
    assert created.status_code == 201

    response = await client.delete(f"{ADMIN_MEDIA}/{created.json()['id']}", headers=ADMIN_HEADERS)

    assert response.status_code == 204
    assert not _path_of(url).exists()


def test_videos_are_never_given_a_generated_thumbnail() -> None:
    storage = FileStorage(get_settings())
    assert storage.owns("/api/v1/files/abc.mp4")
    assert storage.make_thumbnail("/api/v1/files/abc.mp4") is None
