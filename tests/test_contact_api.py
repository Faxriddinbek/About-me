"""Integration tests for the public contact endpoint (validation + rate limit)."""

from __future__ import annotations

from typing import Any

import httpx


def _payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": "Ali Valiyev",
        "email": "ali@example.com",
        "message": "Salom, loyihangiz bo'yicha bog'lanmoqchiman.",
    }
    data.update(overrides)
    return data


def _from_ip(ip: str) -> dict[str, str]:
    # TRUST_PROXY is on in tests, so this sets the client IP the API sees. Each
    # test uses a distinct IP to keep the per-IP rate limiter isolated.
    return {"X-Forwarded-For": ip}


async def test_contact_valid_submission(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/contact", json=_payload(), headers=_from_ip("203.0.113.10")
    )
    assert resp.status_code == 201
    assert resp.json() == {"status": "sent"}


async def test_contact_invalid_email(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/contact",
        json=_payload(email="not-an-email"),
        headers=_from_ip("203.0.113.11"),
    )
    assert resp.status_code == 422


async def test_contact_message_too_short(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/contact",
        json=_payload(message="short"),
        headers=_from_ip("203.0.113.12"),
    )
    assert resp.status_code == 422


async def test_contact_fourth_request_is_rate_limited(client: httpx.AsyncClient) -> None:
    ip = _from_ip("203.0.113.99")
    for _ in range(3):
        ok = await client.post("/api/v1/contact", json=_payload(), headers=ip)
        assert ok.status_code == 201

    blocked = await client.post("/api/v1/contact", json=_payload(), headers=ip)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
