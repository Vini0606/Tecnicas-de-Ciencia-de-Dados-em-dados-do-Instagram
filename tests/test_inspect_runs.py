import json

import pandas as pd

from scripts.inspect_runs import (
    _backfill_report_run_ids,
    _dir_run_ids,
    _parse_timestamp_from_run_id,
    collect,
    print_detail,
    print_list,
)


def test_dir_run_ids_lista_subdiretorios(tmp_path):
    (tmp_path / "run_a").mkdir()
    (tmp_path / "run_b").mkdir()
    (tmp_path / "arquivo_solto.txt").write_text("nao e um run_id")

    assert _dir_run_ids(tmp_path) == {"run_a", "run_b"}


def test_dir_run_ids_diretorio_inexistente(tmp_path):
    assert _dir_run_ids(tmp_path / "nao_existe") == set()


def test_backfill_report_run_ids_le_de_dentro_do_json(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.inspect_runs.settings.DATA_DIR", tmp_path)
    backfill_dir = tmp_path / "backfill"
    backfill_dir.mkdir()
    (backfill_dir / "backfill_report_1d_20260830T190037Z.json").write_text(
        json.dumps({"run_id": "run_backfill_1", "window_days": 1})
    )
    (backfill_dir / "backfill_report_corrompido.json").write_text("{nao e json valido")

    result = _backfill_report_run_ids()

    assert set(result.keys()) == {"run_backfill_1"}


def test_parse_timestamp_from_run_id_formato_build_run_id():
    assert _parse_timestamp_from_run_id("20260830_190146_bffaff02") == "2026-08-30 19:01:46"


def test_parse_timestamp_from_run_id_formato_desconhecido():
    assert _parse_timestamp_from_run_id("a8f36a6f-4644-4588-be24-5bb53d564c57") == "?"


class _FakeDeltaTable:
    """Substitui deltalake.DeltaTable nos testes -- devolve um DataFrame
    fixo por caminho, sem precisar escrever uma tabela Delta de verdade."""

    _tables: dict[str, pd.DataFrame] = {}

    def __init__(self, path, storage_options=None):
        if path not in self._tables:
            raise FileNotFoundError(path)
        self._df = self._tables[path]

    def to_pandas(self):
        return self._df


def test_collect_classifica_extracao_e_modelagem_separadamente(tmp_path, monkeypatch):
    landing_dir = tmp_path / "landing"
    logs_dir = tmp_path / "logs"
    checkpoints_dir = tmp_path / "checkpoints"
    (landing_dir / "run_extracao").mkdir(parents=True)
    (checkpoints_dir / "run_modelagem").mkdir(parents=True)

    monkeypatch.setattr("scripts.inspect_runs.settings.DATA_DIR", tmp_path)
    monkeypatch.setattr("scripts.inspect_runs.settings.LANDING_DIR", landing_dir)
    monkeypatch.setattr("scripts.inspect_runs.settings.LOGS_DIR", logs_dir)
    monkeypatch.setattr("scripts.inspect_runs.settings.MODEL_CHECKPOINTS_DIR", checkpoints_dir)

    _FakeDeltaTable._tables = {
        "bronze_profiles": pd.DataFrame({"_run_id": ["run_extracao", "run_extracao"]}),
        "gold_sentiment": pd.DataFrame({"_run_id": ["run_modelagem"]}),
    }
    monkeypatch.setattr("scripts.inspect_runs.DeltaTable", _FakeDeltaTable)
    monkeypatch.setattr(
        "scripts.inspect_runs.BRONZE_TABLES", {"profiles": "bronze_profiles"}
    )
    monkeypatch.setattr("scripts.inspect_runs.SILVER_TABLES", {})
    monkeypatch.setattr(
        "scripts.inspect_runs.GOLD_TABLES", {"governor_sentiment": "gold_sentiment"}
    )

    records = collect()

    assert records["run_extracao"]["tipo"] == "extracao"
    assert records["run_extracao"]["bronze"] == {"profiles": 2}
    assert records["run_extracao"]["landing"] is True
    assert records["run_extracao"]["checkpoint"] is False

    assert records["run_modelagem"]["tipo"] == "modelagem"
    assert records["run_modelagem"]["gold"] == {"governor_sentiment": 1}
    assert records["run_modelagem"]["checkpoint"] is True
    assert records["run_modelagem"]["landing"] is False


def test_collect_run_recalculado_via_cache_hit_nao_e_classificado_como_modelagem(
    tmp_path, monkeypatch
):
    """governor_engagement e recalculado em toda invocacao de
    run_medallion_pipeline (cache-hit incluso, sem extracao nova nenhuma) --
    sozinho, nao deve classificar o run_id como "modelagem"."""
    monkeypatch.setattr("scripts.inspect_runs.settings.DATA_DIR", tmp_path)
    monkeypatch.setattr("scripts.inspect_runs.settings.LANDING_DIR", tmp_path / "landing")
    monkeypatch.setattr("scripts.inspect_runs.settings.LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(
        "scripts.inspect_runs.settings.MODEL_CHECKPOINTS_DIR", tmp_path / "checkpoints"
    )

    _FakeDeltaTable._tables = {
        "gold_engagement": pd.DataFrame({"_run_id": ["run_cache_hit"]}),
    }
    monkeypatch.setattr("scripts.inspect_runs.DeltaTable", _FakeDeltaTable)
    monkeypatch.setattr("scripts.inspect_runs.BRONZE_TABLES", {})
    monkeypatch.setattr("scripts.inspect_runs.SILVER_TABLES", {})
    monkeypatch.setattr(
        "scripts.inspect_runs.GOLD_TABLES", {"governor_engagement": "gold_engagement"}
    )

    records = collect()

    assert records["run_cache_hit"]["tipo"] == "etl-cache-hit"


def test_print_list_mantem_colunas_alinhadas_com_tipo_longo(capsys):
    """Um valor de "tipo" mais longo que os outros (ex: etl-cache-hit) nao
    pode desalinhar as colunas seguintes -- a largura de cada coluna e
    calculada a partir do conteudo real, nao um chute fixo."""
    records = {
        "run_curto": {
            "tipo": "modelagem",
            "quando": "2026-08-30 19:01:46",
            "landing": False,
            "logs": True,
            "checkpoint": True,
            "backfill_report": None,
            "bronze": {},
            "silver": {},
            "gold": {"governor_sentiment": 10},
        },
        "run_tipo_longo": {
            "tipo": "etl-cache-hit",
            "quando": "2026-08-31 00:03:00",
            "landing": False,
            "logs": True,
            "checkpoint": False,
            "backfill_report": None,
            "bronze": {},
            "silver": {"profiles_clean": 5},
            "gold": {"governor_engagement": 3},
        },
    }

    print_list(records)

    linhas_tabela = [
        linha
        for linha in capsys.readouterr().out.splitlines()
        if linha and not linha.startswith("-") and "=" not in linha
    ]
    larguras = {len(linha) for linha in linhas_tabela}
    assert len(larguras) == 1, f"linhas com larguras diferentes: {linhas_tabela}"


def test_print_list_sem_registros_nao_quebra(capsys):
    print_list({})
    assert "Nenhum run_id encontrado" in capsys.readouterr().out


def test_print_detail_run_id_nao_encontrado(capsys):
    print_detail("run_inexistente", {})
    assert "nao encontrado" in capsys.readouterr().out


def test_print_detail_run_id_encontrado_mostra_fontes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("scripts.inspect_runs.settings.LANDING_DIR", tmp_path / "landing")
    monkeypatch.setattr("scripts.inspect_runs.settings.LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(
        "scripts.inspect_runs.settings.MODEL_CHECKPOINTS_DIR", tmp_path / "checkpoints"
    )
    records = {
        "run_x": {
            "tipo": "extracao",
            "quando": "2026-08-30 19:01:46",
            "landing": True,
            "logs": False,
            "checkpoint": False,
            "backfill_report": None,
            "bronze": {"profiles": 27},
            "silver": {},
            "gold": {},
        }
    }

    print_detail("run_x", records)

    saida = capsys.readouterr().out
    assert "run_x" in saida
    assert "extracao" in saida
    assert "profiles" in saida
