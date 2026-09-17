"""Tests for the startup upload-directory check.

The check exists because both failures it looks for are silent: a read-only
mount only surfaces when someone uploads, and a missing volume only surfaces
after a deploy has already discarded the images. These tests pin that it stays
loud in production and quiet when the directory is mounted as intended.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.main import _check_upload_dir

_NOT_MOUNTED = "not a mount point"


def _settings(tmp_path: Path, *, environment: str = "prod") -> Settings:
    """Build settings pointing at a throwaway upload directory.

    Values are passed explicitly so the surrounding environment (and any local
    ``.env``) cannot change what a test is asserting.
    """
    return Settings(
        ENVIRONMENT=environment,
        DEBUG=False,
        DATABASE_URL="postgresql+asyncpg://user:pass@db:5432/portfolio",
        ADMIN_TOKEN="a-long-enough-test-token",
        UPLOAD_DIR=str(tmp_path / "uploads"),
    )


def test_warns_in_prod_when_upload_dir_is_not_a_mount_point(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A plain directory in production means the images die with the container."""
    with caplog.at_level(logging.WARNING):
        _check_upload_dir(_settings(tmp_path))

    assert any(_NOT_MOUNTED in record.message for record in caplog.records)


def test_silent_in_prod_when_upload_dir_is_mounted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mounted volume is the correct setup, so it must not cry wolf."""
    monkeypatch.setattr("app.main.os.path.ismount", lambda _path: True)

    with caplog.at_level(logging.WARNING):
        _check_upload_dir(_settings(tmp_path))

    assert caplog.records == []


def test_silent_in_dev_without_a_mount(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Locally the directory is a normal folder; warning about it is just noise."""
    with caplog.at_level(logging.WARNING):
        _check_upload_dir(_settings(tmp_path, environment="dev"))

    assert caplog.records == []


def test_logs_an_error_when_upload_dir_is_not_writable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read-only mount is reported at startup rather than on the first upload."""

    def deny(self: Path, *args: Any, **kwargs: Any) -> int:
        raise OSError("read-only file system")

    monkeypatch.setattr(Path, "write_bytes", deny)

    with caplog.at_level(logging.ERROR):
        _check_upload_dir(_settings(tmp_path))

    assert any("not writable" in record.message for record in caplog.records)
