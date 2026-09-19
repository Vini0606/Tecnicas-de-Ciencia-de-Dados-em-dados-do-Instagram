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


def test_write_and_read_ugc_mentions(tmp_path):
    """ADR 0020 (Ficha 8) / issue #93: write_ugc_mentions só funciona quando
    bronze_ugc_mentions_path foi configurado -- opcional de propósito, nem
    todo chamador de BronzeWriter precisa dele."""
    writer = BronzeWriter(
        tmp_path / "profiles",
        tmp_path / "posts",
        tmp_path / "reels",
        bronze_ugc_mentions_path=tmp_path / "ugc_mentions",
    )

    sample = [{"id": "m1", "ownerUsername": "eleitor_1"}]
    run_id = writer.write_ugc_mentions(sample, run_id="run-ugc")
    assert isinstance(run_id, str)

    df = writer.get_latest_ugc_mentions()
    assert "_run_id" in df.columns
    assert (df["_run_id"] == "run-ugc").all()


def test_write_ugc_mentions_sem_path_configurado_levanta_erro(tmp_path):
    writer = BronzeWriter(tmp_path / "profiles", tmp_path / "posts", tmp_path / "reels")

    with pytest.raises(KeyError):
        writer.write_ugc_mentions([{"id": "m1"}])
