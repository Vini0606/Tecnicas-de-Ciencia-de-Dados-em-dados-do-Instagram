import json

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


def test_bronze_nova_coleta_substitui_a_anterior(tmp_path):
    """ADR 0039: uma Coleta substitui a outra -- a Bronze não acumula run_id."""
    writer = BronzeWriter(tmp_path / "profiles", tmp_path / "posts", tmp_path / "reels")

    writer.write_profiles([{"id": "1", "username": "a"}], run_id="run-001")
    writer.write_profiles([{"id": "2", "username": "b"}], run_id="run-002")

    df = writer.get_latest_profiles()
    assert len(df) == 1
    assert df["_run_id"].tolist() == ["run-002"]


def test_bronze_guarda_o_item_completo_inclusive_campos_fora_do_schema(tmp_path):
    """ADR 0039: nenhum campo da Apify é descartado -- `_raw` reproduz o item."""
    writer = BronzeWriter(tmp_path / "profiles", tmp_path / "posts", tmp_path / "reels")
    item = {
        "id": "p1",
        "ownerUsername": "gov1",
        "campoNovoDaApify": {"a": [1, 2], "b": "ç"},
        "hashtags": ["x", "y"],
    }

    writer.write_posts([item], run_id="run-1")

    df = writer.get_latest_posts()
    assert json.loads(df["_raw"].iloc[0]) == item


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


def test_write_reels_converte_owner_id_numerico_para_string(tmp_path):
    """Issue #229: a Apify devolveu `ownerId` como int em 2 de 522 reels reais
    (2026-10-06), e a Bronze abortava a extração inteira na conversão para o
    `pa.string()` do schema."""
    writer = BronzeWriter(tmp_path / "profiles", tmp_path / "posts", tmp_path / "reels")

    writer.write_reels(
        [
            {"id": "r1", "ownerId": "111"},
            {"id": "r2", "ownerId": 222},
            {"id": "r3", "ownerId": 333.0},
            {"id": "r4", "ownerId": None},
        ],
        run_id="run_1",
    )

    out = writer.get_latest_reels().set_index("id")["ownerId"]
    assert out[["r1", "r2", "r3"]].tolist() == ["111", "222", "333"]
    assert pd.isna(out["r4"])
