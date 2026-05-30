from pathlib import Path

import pytest

from config import settings
from src.repositories.delta_repository import DeltaRepository


def _skip_if_missing(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"Delta path not found: {path}")


def test_load_profiles_from_delta():
    _skip_if_missing(settings.GOLD_ENGAGEMENT)
    repo = DeltaRepository(settings.GOLD_DIR, settings.SILVER_DIR)
    df = repo.load_profiles()
    assert not df.empty
    assert "username" in df.columns
    assert "followersCount" in df.columns


def test_load_comments_from_delta():
    _skip_if_missing(settings.SILVER_COMMENTS)
    repo = DeltaRepository(settings.GOLD_DIR, settings.SILVER_DIR)
    df = repo.load_comments()
    assert not df.empty
    assert "inputUrl" in df.columns
    assert "text" in df.columns


def test_load_reels_from_delta():
    _skip_if_missing(settings.SILVER_REELS)
    repo = DeltaRepository(settings.GOLD_DIR, settings.SILVER_DIR)
    df = repo.load_reels()
    assert not df.empty
    assert "id" in df.columns
    assert "inputUrl" in df.columns
