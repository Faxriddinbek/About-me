"""Application configuration loaded from the environment.

Centralising configuration here keeps secrets and environment-specific values
out of the code. Everything is read once, validated, and cached so the rest of
the application can depend on a single, consistent ``Settings`` instance rather
than re-reading the environment ad hoc.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Local-dev fallback database. Requires no running server, so a fresh clone boots
# with zero setup. Production MUST override this with a real async Postgres DSN.
_SQLITE_FALLBACK = "sqlite+aiosqlite:///./portfolio.db"


class Settings(BaseSettings):
    """Typed application settings sourced from environment variables / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---------------------------------------------------------
    APP_NAME: str = "Portfolio API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["dev", "prod"] = "dev"
    DEBUG: bool = True

    # --- Database ------------------------------------------------------------
    # Async-driver DSN. Use ``postgresql+asyncpg://user:pass@host/db`` in prod.
    DATABASE_URL: str = _SQLITE_FALLBACK

    # --- CORS ----------------------------------------------------------------
    # Comma-separated list of allowed origins. Kept as a raw string because
    # pydantic-settings would otherwise try to JSON-decode a list-typed env var,
    # which breaks the simple comma-separated form we want operators to use.
    CORS_ORIGINS: str = "http://localhost:3000"

    # --- Secrets -------------------------------------------------------------
    ADMIN_TOKEN: str = ""  # required in prod; guards write endpoints

    # --- Telegram (optional) -------------------------------------------------
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    @property
    def cors_origins(self) -> list[str]:
        """Parse the raw comma-separated origins into a clean, de-blanked list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_prod(self) -> bool:
        return self.ENVIRONMENT == "prod"

    @property
    def is_dev(self) -> bool:
        return self.ENVIRONMENT == "dev"

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> Settings:
        """Fail loudly at startup when production is missing required secrets.

        Validating here (rather than at first use) means a misconfigured
        deployment crashes immediately and visibly, instead of silently running
        with an insecure or non-functional configuration.
        """
        if self.is_prod:
            missing: list[str] = []
            if not self.ADMIN_TOKEN:
                missing.append("ADMIN_TOKEN")
            if self.DATABASE_URL.startswith("sqlite"):
                missing.append("DATABASE_URL (must be a real database in prod)")
            if missing:
                raise ValueError(
                    "Missing required production configuration: " + ", ".join(missing)
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached ``Settings`` singleton.

    ``lru_cache`` guarantees the environment is read and validated exactly once
    per process. Import this everywhere instead of constructing ``Settings``
    directly, so the whole app shares one validated configuration.
    """
    return Settings()
