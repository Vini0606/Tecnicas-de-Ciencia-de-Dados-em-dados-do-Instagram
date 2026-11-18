"""BronzeWriter só escreve (ADR 0046); a leitura nos testes de round-trip é
pelo `DeltaRepository`, com o layout padrão `bronze/<tabela>`."""

import json

import pandas as pd
import pytest

from src.data_extract.bronze_writer import BronzeWriter
from src.repositories.delta_repository import DeltaRepository


def _writer(tmp_path, com_ugc=False):
    return BronzeWriter(
        tmp_path / "instagram_profiles",
        tmp_path / "instagram_posts",
        tmp_path / "instagram_reels",
        bronze_ugc_mentions_path=(tmp_path / "ugc_mentions") if com_ugc else None,
    )


def _repo(tmp_path):
    return DeltaRepository(gold_dir=tmp_path / "gold", bronze_dir=tmp_path)


def test_bronze_write_and_read(tmp_path):
    writer = _writer(tmp_path)

    sample = [{"id": "1", "username": "a"}]
    run_id = writer.write_profiles(sample, run_id="run-test")
    assert isinstance(run_id, str)

    df = _repo(tmp_path).load_bronze_profiles()
    assert "_run_id" in df.columns
    assert (df["_run_id"] == "run-test").all()


def test_bronze_nova_coleta_substitui_a_anterior(tmp_path):
    """ADR 0039: uma Coleta substitui a outra -- a Bronze não acumula run_id."""
    writer = _writer(tmp_path)

    writer.write_profiles([{"id": "1", "username": "a"}], run_id="run-001")
    writer.write_profiles([{"id": "2", "username": "b"}], run_id="run-002")

    df = _repo(tmp_path).load_bronze_profiles()
    assert len(df) == 1
    assert df["_run_id"].tolist() == ["run-002"]


def test_bronze_guarda_o_item_completo_inclusive_campos_fora_do_schema(tmp_path):
    """ADR 0039: nenhum campo da Apify é descartado -- `_raw` reproduz o item."""
    writer = _writer(tmp_path)
    item = {
        "id": "p1",
        "ownerUsername": "gov1",
        "campoNovoDaApify": {"a": [1, 2], "b": "ç"},
        "hashtags": ["x", "y"],
    }

    writer.write_posts([item], run_id="run-1")

    df = _repo(tmp_path).load_bronze_posts()
    assert json.loads(df["_raw"].iloc[0]) == item


def test_write_empty_data_raises(tmp_path):
    writer = _writer(tmp_path)

    with pytest.raises(ValueError, match="Nenhum dado fornecido"):
        writer.write_profiles([])


def test_historico_delta_da_bronze_e_lido_pelo_repositorio(tmp_path):
    writer = _writer(tmp_path)
    writer.write_profiles([{"id": "1"}], run_id="run-hist")

    history = _repo(tmp_path).get_table_history("instagram_profiles", layer="bronze")
    assert isinstance(history, pd.DataFrame)
    assert len(history) >= 1


def test_write_and_read_ugc_mentions(tmp_path):
    """ADR 0020 (Ficha 8) / issue #93: write_ugc_mentions só funciona quando
    bronze_ugc_mentions_path foi configurado -- opcional de propósito, nem
    todo chamador de BronzeWriter precisa dele."""
    writer = _writer(tmp_path, com_ugc=True)

    sample = [{"id": "m1", "ownerUsername": "eleitor_1"}]
    run_id = writer.write_ugc_mentions(sample, run_id="run-ugc")
    assert isinstance(run_id, str)

    df = _repo(tmp_path).load_bronze_ugc_mentions()
    assert "_run_id" in df.columns
    assert (df["_run_id"] == "run-ugc").all()


def test_write_ugc_mentions_sem_path_configurado_levanta_erro(tmp_path):
    writer = _writer(tmp_path)

    with pytest.raises(KeyError):
        writer.write_ugc_mentions([{"id": "m1"}])


def test_write_reels_converte_owner_id_numerico_para_string(tmp_path):
    """Issue #229: a Apify devolveu `ownerId` como int em 2 de 522 reels reais
    (2026-10-06), e a Bronze abortava a extração inteira na conversão para o
    `pa.string()` do schema."""
    writer = _writer(tmp_path)

    writer.write_reels(
        [
            {"id": "r1", "ownerId": "111"},
            {"id": "r2", "ownerId": 222},
            {"id": "r3", "ownerId": 333.0},
            {"id": "r4", "ownerId": None},
        ],
        run_id="run_1",
    )

    out = _repo(tmp_path).load_bronze_reels().set_index("id")["ownerId"]
    assert out[["r1", "r2", "r3"]].tolist() == ["111", "222", "333"]
    assert pd.isna(out["r4"])


def test_bronze_writer_nao_le(tmp_path):
    """ADR 0046: a classe de escrita não expõe leitura; quem lê é o repositório."""
    writer = _writer(tmp_path)

    assert not [m for m in dir(writer) if m.startswith("get_")]
