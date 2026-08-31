import pandas as pd
from deltalake.writer import write_deltalake

from src.repositories import delta_repository
from src.repositories.delta_repository import DeltaRepository


def test_delta_repository_com_uri_s3_nao_corrompe_a_uri(monkeypatch):
    # Regressão: DeltaRepository usava pathlib.Path para juntar caminhos, e
    # Path colapsa barras duplas -- "s3://bucket/gold" virava "s3:/bucket/gold".
    captured = {}

    class FakeDeltaTable:
        def __init__(self, path, storage_options=None):
            captured["path"] = path

        def to_pandas(self):
            return pd.DataFrame({"id": ["1"]})

    monkeypatch.setattr(delta_repository, "DeltaTable", FakeDeltaTable)

    repo = DeltaRepository(gold_dir="s3://meu-bucket/gold")
    repo.load_profiles()

    assert captured["path"] == "s3://meu-bucket/gold/governor_engagement"


def test_delta_repository_basic(tmp_path):
    gold = tmp_path
    engagement_path = gold / "governor_engagement"
    df = pd.DataFrame(
        {
            "id": ["1"],
            "username": ["g"],
            "TOTAL ENGAJAMENTO": [10],
            "% ENGAJAMENTO": [0.1],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    write_deltalake(str(engagement_path), df, mode="overwrite")

    repo = DeltaRepository(gold_dir=gold)
    out = repo.load_profiles()
    assert "% ENGAJAMENTO" in out.columns


def test_load_engagement_history_acumula_varias_execucoes(tmp_path):
    gold = tmp_path
    history_path = gold / "governor_engagement_history"
    df_r1 = pd.DataFrame(
        {
            "id": ["1"],
            "username": ["g"],
            "TOTAL ENGAJAMENTO": [10],
            "% ENGAJAMENTO": [0.1],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    df_r2 = pd.DataFrame(
        {
            "id": ["1"],
            "username": ["g"],
            "TOTAL ENGAJAMENTO": [20],
            "% ENGAJAMENTO": [0.2],
            "_run_id": ["r2"],
            "_generated_at": pd.to_datetime(["2026-05-02"], utc=True),
        }
    )
    write_deltalake(str(history_path), df_r1, mode="overwrite")
    write_deltalake(str(history_path), df_r2, mode="append")

    repo = DeltaRepository(gold_dir=gold)
    out = repo.load_engagement_history()

    assert len(out) == 2
    assert set(out["_run_id"]) == {"r1", "r2"}
