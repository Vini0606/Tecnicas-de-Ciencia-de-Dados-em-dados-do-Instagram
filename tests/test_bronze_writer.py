import pandas as pd
import pytest

from src.data_extract.bronze_writer import BronzeWriter


def test_bronze_write_and_read(tmp_path):
    profiles_path = tmp_path / "profiles"
    posts_path = tmp_path / "posts"
    reels_path = tmp_path / "reels"

    writer = BronzeWriter(profiles_path, posts_path, reels_path)

    sample = [{"id": "1", "username": "a"}]
    run_id = writer.write_profiles(sample, run_id="run-test")
    assert isinstance(run_id, str)

    df = writer.get_latest_profiles()
    assert "_run_id" in df.columns
    assert (df["_run_id"] == "run-test").all()


def test_bronze_is_append_only(tmp_path):
    profiles_path = tmp_path / "profiles"
    posts_path = tmp_path / "posts"
    reels_path = tmp_path / "reels"

    writer = BronzeWriter(profiles_path, posts_path, reels_path)

    writer.write_profiles([{"id": "1", "username": "a"}], run_id="run-001")
    writer.write_profiles([{"id": "2", "username": "b"}], run_id="run-002")

    df = writer.get_latest_profiles()
    assert len(df) == 2
    assert df["_run_id"].nunique() == 2


def test_write_empty_data_raises(tmp_path):
    profiles_path = tmp_path / "profiles"
    posts_path = tmp_path / "posts"
    reels_path = tmp_path / "reels"

    writer = BronzeWriter(profiles_path, posts_path, reels_path)

    with pytest.raises(ValueError, match="Nenhum dado fornecido"):
        writer.write_profiles([])


def test_get_history_returns_dataframe(tmp_path):
    profiles_path = tmp_path / "profiles"
    posts_path = tmp_path / "posts"
    reels_path = tmp_path / "reels"

    writer = BronzeWriter(profiles_path, posts_path, reels_path)
    writer.write_profiles([{"id": "1"}], run_id="run-hist")

    history = writer.get_history("profiles")
    assert isinstance(history, pd.DataFrame)
    assert len(history) >= 1
