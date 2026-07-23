"""Smoke tests proving the application boots and its wiring is sound."""

from __future__ import annotations

import httpx


async def test_health_ok(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"]


async def test_request_id_header_present(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.headers.get("X-Request-ID")


async def test_client_supplied_request_id_is_echoed(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert resp.headers.get("X-Request-ID") == "abc-123"
