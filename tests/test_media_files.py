"""A media item and the file behind it are deleted together.

The risk these tests guard is asymmetric. Leaving a file behind wastes a few
kilobytes; deleting a file that is still referenced — or one that was never
ours, like a YouTube link — cannot be undone. So most of what follows checks
that nothing is deleted when it should not be.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.db.session import get_session
from app.main import create_app
from app.services.storage import FileStorage
from scripts.cleanup_orphans import select_orphans
from tests.conftest import ADMIN_HEADERS
from tests.test_files_api import PNG_BYTES, upload_files

ADMIN_MEDIA = "/api/v1/admin/media"
UPLOAD_URL = f"{ADMIN_MEDIA}/upload"
YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


async def _upload(client: httpx.AsyncClient, name: str = "photo.png") -> str:
    """Upload an image and return its URL."""
    response = await client.post(
        UPLOAD_URL, headers=ADMIN_HEADERS, files=upload_files(name, PNG_BYTES)
    )
    assert response.status_code == 201
    return response.json()["url"]


async def _create_media(client: httpx.AsyncClient, **fields: object) -> int:
    payload: dict[str, object] = {"media_type": "photo", **fields}
    response = await client.post(ADMIN_MEDIA, headers=ADMIN_HEADERS, json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def _path_of(url: str) -> Path:
    return get_settings().upload_path / Path(url).name


async def test_deleting_media_deletes_its_file(client: httpx.AsyncClient) -> None:
    url = await _upload(client)
    media_id = await _create_media(client, url=url)
    assert _path_of(url).is_file()

    response = await client.delete(f"{ADMIN_MEDIA}/{media_id}", headers=ADMIN_HEADERS)

    assert response.status_code == 204
    assert not _path_of(url).exists()


async def test_deleting_media_deletes_its_cover_image_too(
    client: httpx.AsyncClient,
) -> None:
    """A video's cover is an uploaded file of its own, and just as orphaned."""
    cover = await _upload(client, "cover.png")
    media_id = await _create_media(
        client, media_type="video", url=YOUTUBE_URL, thumbnail_url=cover
    )

    response = await client.delete(f"{ADMIN_MEDIA}/{media_id}", headers=ADMIN_HEADERS)

    assert response.status_code == 204
    assert not _path_of(cover).exists()


async def test_deleting_media_leaves_external_links_alone(
    client: httpx.AsyncClient,
) -> None:
    """Nothing of ours lives behind a YouTube link; deletion must be a no-op."""
    media_id = await _create_media(client, media_type="video", url=YOUTUBE_URL)

    response = await client.delete(f"{ADMIN_MEDIA}/{media_id}", headers=ADMIN_HEADERS)

    assert response.status_code == 204


async def test_deleting_media_whose_file_is_already_gone_still_succeeds(
    client: httpx.AsyncClient,
) -> None:
    """A missing file is not a reason to keep an undeletable row in the admin."""
    url = await _upload(client)
    media_id = await _create_media(client, url=url)
    _path_of(url).unlink()

    response = await client.delete(f"{ADMIN_MEDIA}/{media_id}", headers=ADMIN_HEADERS)

    assert response.status_code == 204


async def test_replacing_a_url_deletes_the_previous_file(
    client: httpx.AsyncClient,
) -> None:
    old = await _upload(client, "old.png")
    new = await _upload(client, "new.png")
    media_id = await _create_media(client, url=old)

    response = await client.patch(
        f"{ADMIN_MEDIA}/{media_id}", headers=ADMIN_HEADERS, json={"url": new}
    )

    assert response.status_code == 200
    assert not _path_of(old).exists()
    assert _path_of(new).is_file()


async def test_editing_other_fields_keeps_the_file(client: httpx.AsyncClient) -> None:
    """Renaming a photo must not cost you the photo."""
    url = await _upload(client)
    media_id = await _create_media(client, url=url, title_uz="Eski")

    response = await client.patch(
        f"{ADMIN_MEDIA}/{media_id}", headers=ADMIN_HEADERS, json={"title_uz": "Yangi"}
    )

    assert response.status_code == 200
    assert _path_of(url).is_file()


async def test_resubmitting_the_same_url_keeps_the_file(
    client: httpx.AsyncClient,
) -> None:
    """The admin form sends every field back, unchanged ones included."""
    url = await _upload(client)
    media_id = await _create_media(client, url=url)

    response = await client.patch(
        f"{ADMIN_MEDIA}/{media_id}",
        headers=ADMIN_HEADERS,
        json={"url": url, "title_uz": "Sarlavha"},
    )

    assert response.status_code == 200
    assert _path_of(url).is_file()


@pytest.fixture
async def failing_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
    """A client whose requests fail at commit time, like a database outage would."""
    application = create_app()

    async def commit_fails() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session
            # Raised where the real dependency commits, so the request dies at
            # exactly the moment the transaction would have been made permanent.
            raise RuntimeError("commit failed")

    application.dependency_overrides[get_session] = commit_fails
    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_a_failed_commit_keeps_the_file(
    client: httpx.AsyncClient, failing_client: httpx.AsyncClient
) -> None:
    """The reason deletion is deferred: a lost file cannot be recovered.

    If the transaction never commits, the media item is still there — and its
    file must be too, or the admin is left with a row pointing at nothing.
    """
    url = await _upload(client)
    media_id = await _create_media(client, url=url)

    response = await failing_client.delete(
        f"{ADMIN_MEDIA}/{media_id}", headers=ADMIN_HEADERS
    )

    assert response.status_code == 500
    assert _path_of(url).is_file()


class TestOwnership:
    """``FileStorage.owns`` is the single gate in front of every deletion."""

    def test_accepts_a_url_this_service_produced(self) -> None:
        assert FileStorage.owns("/api/v1/files/abc123.png")

    def test_rejects_external_and_malformed_urls(self) -> None:
        for url in [
            None,
            "",
            YOUTUBE_URL,
            "https://cdn.example/photo.jpg",
            "https://evil.example/api/v1/files/photo.png",  # prefix, but not ours
            "/api/v1/files/",  # no filename
            "/api/v1/files/../../.env",  # traversal
            "/api/v1/files/notes.txt",  # not an image we store
        ]:
            assert not FileStorage.owns(url), url


class TestOrphanSelection:
    """The cleanup script's rule, without a database or a real upload directory."""

    def test_reports_only_unreferenced_files(self, tmp_path: Path) -> None:
        used = tmp_path / "used.png"
        stray = tmp_path / "stray.png"
        for path in (used, stray):
            path.write_bytes(PNG_BYTES)

        orphans = select_orphans([used, stray], {"used.png"}, cutoff=time.time())

        assert orphans == [stray]

    def test_spares_files_that_are_too_young(self, tmp_path: Path) -> None:
        """A just-uploaded file may belong to an admin form nobody saved yet."""
        fresh = tmp_path / "fresh.png"
        fresh.write_bytes(PNG_BYTES)

        orphans = select_orphans([fresh], set(), cutoff=time.time() - 3600)

        assert orphans == []
