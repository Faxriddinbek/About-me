"""Shared slowapi limiter.

Defined in its own module so routes and the application factory import the same
``Limiter`` instance. The key function is proxy-aware (see ``get_client_ip``):
behind a trusted proxy the real client IP comes from ``X-Forwarded-For``.
"""

from __future__ import annotations

from slowapi import Limiter

from app.api.deps import get_client_ip

limiter = Limiter(key_func=get_client_ip)
