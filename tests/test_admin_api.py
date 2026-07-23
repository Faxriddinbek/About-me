"""Integration tests for admin authentication and endpoints."""

from __future__ import annotations

from typing import Any

import httpx

from tests.conftest import ADMIN_HEADERS


def _project_payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title_uz": "Yangi",
        "title_en": "New",
        "description_uz": "uz",
        "description_en": "en",
        "tags": ["x"],
    }
    data.update(overrides)
    return data


def _media_payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "media_type": "photo",
        "url": "https://cdn.example/x.jpg",
        "title_uz": "Rasm",
        "title_en": "Photo",
    }
    data.update(overrides)
    return data


async def test_admin_requires_token(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/admin/projects", json=_project_payload())
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_admin_rejects_wrong_token(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/admin/projects",
        json=_project_payload(),
        headers={"X-Admin-Token": "wrong-token"},
    )
    assert resp.status_code == 401


async def test_admin_accepts_correct_token(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/admin/projects", json=_project_payload(), headers=ADMIN_HEADERS
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Yangi"  # default admin language is Uzbek
    assert body["id"] >= 1

    # The created project now shows up in the public list.
    public = await client.get("/api/v1/projects")
    assert public.json()["total"] == 1


async def test_admin_project_full_crud(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/v1/admin/projects", json=_project_payload(), headers=ADMIN_HEADERS
    )
    project_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/admin/projects/{project_id}",
        json={"title_uz": "Ozgargan"},
        headers=ADMIN_HEADERS,
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Ozgargan"

    deleted = await client.delete(
        f"/api/v1/admin/projects/{project_id}", headers=ADMIN_HEADERS
    )
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/projects/{project_id}")).status_code == 404


async def test_admin_media_requires_token(client: httpx.AsyncClient) -> None:
    assert (
        await client.post("/api/v1/admin/media", json=_media_payload())
    ).status_code == 401


async def test_admin_media_full_crud(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/v1/admin/media", json=_media_payload(), headers=ADMIN_HEADERS
    )
    assert created.status_code == 201
    media_id = created.json()["id"]
    assert created.json()["media_type"] == "photo"

    # The new item is visible in the public gallery.
    assert (await client.get("/api/v1/media")).json()["total"] == 1

    updated = await client.patch(
        f"/api/v1/admin/media/{media_id}",
        json={"title_uz": "Yangi rasm"},
        headers=ADMIN_HEADERS,
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Yangi rasm"

    deleted = await client.delete(
        f"/api/v1/admin/media/{media_id}", headers=ADMIN_HEADERS
    )
    assert deleted.status_code == 204
    assert (await client.get("/api/v1/media")).json()["total"] == 0


async def test_admin_contacts_list_and_mark_read(client: httpx.AsyncClient) -> None:
    # A public submission creates an unread message.
    await client.post(
        "/api/v1/contact",
        json={
            "name": "Ali Valiyev",
            "email": "ali@example.com",
            "message": "Salom dunyo, bu bir test xabari.",
        },
        headers={"X-Forwarded-For": "203.0.113.50"},
    )

    # Listing requires a token.
    assert (await client.get("/api/v1/admin/contacts")).status_code == 401

    unread = await client.get(
        "/api/v1/admin/contacts", params={"unread_only": "true"}, headers=ADMIN_HEADERS
    )
    assert unread.status_code == 200
    assert unread.json()["total"] == 1
    message_id = unread.json()["items"][0]["id"]

    marked = await client.patch(
        f"/api/v1/admin/contacts/{message_id}/read", headers=ADMIN_HEADERS
    )
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True

    unread_after = await client.get(
        "/api/v1/admin/contacts", params={"unread_only": "true"}, headers=ADMIN_HEADERS
    )
    assert unread_after.json()["total"] == 0
