"""Integration tests for the public API (projects and media)."""

from __future__ import annotations

from typing import Any

import httpx

from app.models import MediaItem, MediaType, Project


def _project(**overrides: Any) -> Project:
    data: dict[str, Any] = {
        "title_uz": "Loyiha",
        "title_en": "Project",
        "description_uz": "Tavsif",
        "description_en": "Description",
        "tags": ["python"],
        "display_order": 0,
        "is_visible": True,
    }
    data.update(overrides)
    return Project(**data)


async def test_list_projects_shape_and_language(
    client: httpx.AsyncClient, seed: Any
) -> None:
    await seed(
        _project(title_uz="Birinchi", title_en="First", display_order=1),
        _project(title_uz="Ikkinchi", title_en="Second", display_order=2),
    )

    resp = await client.get("/api/v1/projects")  # default lang = uz
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"items", "total", "limit", "offset"}
    assert body["total"] == 2
    assert body["limit"] == 20 and body["offset"] == 0
    assert [item["title"] for item in body["items"]] == ["Birinchi", "Ikkinchi"]
    # Bilingual storage columns must not leak into the response.
    assert "title_uz" not in body["items"][0]

    resp_en = await client.get("/api/v1/projects", params={"lang": "en"})
    assert [item["title"] for item in resp_en.json()["items"]] == ["First", "Second"]


async def test_projects_pagination_bounds(client: httpx.AsyncClient, seed: Any) -> None:
    await seed(*[_project(display_order=i) for i in range(3)])

    resp = await client.get("/api/v1/projects", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2
    assert resp.json()["total"] == 3

    resp_offset = await client.get("/api/v1/projects", params={"limit": 2, "offset": 2})
    assert len(resp_offset.json()["items"]) == 1

    # limit above the cap and an invalid language are rejected with 422.
    assert (await client.get("/api/v1/projects", params={"limit": 101})).status_code == 422
    assert (await client.get("/api/v1/projects", params={"lang": "fr"})).status_code == 422


async def test_invisible_projects_excluded(client: httpx.AsyncClient, seed: Any) -> None:
    await seed(
        _project(title_uz="Korinadi", is_visible=True),
        _project(title_uz="Yashirin", is_visible=False),
    )

    body = (await client.get("/api/v1/projects")).json()
    assert body["total"] == 1
    assert [item["title"] for item in body["items"]] == ["Korinadi"]


async def test_get_project_and_404(client: httpx.AsyncClient, seed: Any) -> None:
    await seed(_project(title_uz="Yagona", title_en="Only"))

    resp = await client.get("/api/v1/projects/1")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Yagona"

    missing = await client.get("/api/v1/projects/9999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


async def test_list_media_filter_and_language_fallback(
    client: httpx.AsyncClient, seed: Any
) -> None:
    await seed(
        MediaItem(
            media_type=MediaType.PHOTO,
            url="https://x/a.jpg",
            title_uz="Rasm",
            title_en="Photo",
            display_order=1,
        ),
        # No English title -> should fall back to Uzbek when lang=en.
        MediaItem(
            media_type=MediaType.VIDEO,
            url="https://x/b.mp4",
            title_uz="Video",
            display_order=2,
        ),
    )

    all_media = await client.get("/api/v1/media")
    assert all_media.status_code == 200
    assert all_media.json()["total"] == 2

    resp_en = await client.get("/api/v1/media", params={"lang": "en"})
    titles = {item["media_type"]: item["title"] for item in resp_en.json()["items"]}
    assert titles["photo"] == "Photo"
    assert titles["video"] == "Video"  # Uzbek fallback

    photos = await client.get("/api/v1/media", params={"type": "photo"})
    assert photos.json()["total"] == 1
    assert photos.json()["items"][0]["media_type"] == "photo"

    assert (await client.get("/api/v1/media", params={"type": "audio"})).status_code == 422


async def test_media_pagination_bounds(client: httpx.AsyncClient, seed: Any) -> None:
    await seed(
        *[
            MediaItem(
                media_type=MediaType.PHOTO, url=f"https://x/{i}.jpg", display_order=i
            )
            for i in range(3)
        ]
    )

    resp = await client.get("/api/v1/media", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2
    assert resp.json()["total"] == 3

    # limit above the cap is rejected.
    assert (await client.get("/api/v1/media", params={"limit": 101})).status_code == 422
