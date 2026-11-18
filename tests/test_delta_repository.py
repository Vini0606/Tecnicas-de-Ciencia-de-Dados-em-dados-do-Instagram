import pandas as pd
import pytest
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


def test_load_sentiment_history_acumula_varias_execucoes(tmp_path):
    gold = tmp_path
    history_path = gold / "governor_sentiment_history"
    df_r1 = pd.DataFrame(
        {
            "id_comment": ["c1"],
            "sentiment_label": ["Positive"],
            "sentiment_score": [0.9],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    df_r2 = pd.DataFrame(
        {
            "id_comment": ["c2"],
            "sentiment_label": ["Negative"],
            "sentiment_score": [0.7],
            "_run_id": ["r2"],
            "_generated_at": pd.to_datetime(["2026-05-08"], utc=True),
        }
    )
    write_deltalake(str(history_path), df_r1, mode="overwrite")
    write_deltalake(str(history_path), df_r2, mode="append")

    repo = DeltaRepository(gold_dir=gold)
    out = repo.load_sentiment_history()

    assert len(out) == 2
    assert set(out["_run_id"]) == {"r1", "r2"}


def test_load_content_topic_priority_score_le_tabela_gold(tmp_path):
    # Spec #182 / issue #190-#191.
    df = pd.DataFrame({"Topic": [0, 1], "Name": ["a", "b"], "score": [0.5, 0.2]})
    write_deltalake(str(tmp_path / "content_topic_priority_score"), df, mode="overwrite")

    out = DeltaRepository(gold_dir=tmp_path).load_content_topic_priority_score()

    assert list(out["Topic"]) == [0, 1]


def test_load_governor_scorecard_le_tabela_gold(tmp_path):
    # ADR 0030 / issue #188.
    df = pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "escore": [61.5],
            "ranking": [1],
        }
    )
    write_deltalake(str(tmp_path / "governor_scorecard"), df, mode="overwrite")

    out = DeltaRepository(gold_dir=tmp_path).load_governor_scorecard()

    assert out["escore"].iloc[0] == 61.5


def test_load_post_comments_le_tabela_silver(tmp_path):
    # Issue #212.
    df = pd.DataFrame({"id_post": ["p1"], "id_comment": ["c1"]})
    write_deltalake(str(tmp_path / "silver" / "post_comments_clean"), df, mode="overwrite")

    out = DeltaRepository(gold_dir=tmp_path / "gold", silver_dir=tmp_path / "silver").load_post_comments()

    assert list(out["id_comment"]) == ["c1"]


# --- Issue #313: o repositório cobre a Bronze e as Silver que faltavam -----


def _repo_tres_camadas(tmp_path):
    return DeltaRepository(
        gold_dir=tmp_path / "gold",
        silver_dir=tmp_path / "silver",
        bronze_dir=tmp_path / "bronze",
    )


@pytest.mark.parametrize(
    ("acessor", "tabela"),
    [
        ("load_bronze_profiles", "instagram_profiles"),
        ("load_bronze_posts", "instagram_posts"),
        ("load_bronze_reels", "instagram_reels"),
        ("load_bronze_ugc_mentions", "ugc_mentions"),
    ],
)
def test_load_bronze_le_a_tabela_certa_de_bronze_dir(tmp_path, acessor, tabela):
    df = pd.DataFrame({"id": ["1"], "_raw": ["{}"], "_run_id": ["r1"]})
    write_deltalake(str(tmp_path / "bronze" / tabela), df, mode="overwrite")

    out = getattr(_repo_tres_camadas(tmp_path), acessor)()

    assert list(out["_raw"]) == ["{}"]


@pytest.mark.parametrize(
    ("acessor", "tabela"),
    [
        ("load_silver_profiles", "profiles_clean"),
        ("load_silver_comments", "comments_clean"),
        ("load_silver_ugc_mentions", "ugc_mentions"),
    ],
)
def test_load_silver_le_a_tabela_certa_de_silver_dir(tmp_path, acessor, tabela):
    df = pd.DataFrame({"id": ["1"], "_source_layer": ["bronze"]})
    write_deltalake(str(tmp_path / "silver" / tabela), df, mode="overwrite")

    out = getattr(_repo_tres_camadas(tmp_path), acessor)()

    assert list(out["_source_layer"]) == ["bronze"]


def test_load_silver_comments_nao_cai_na_gold_como_load_comments(tmp_path):
    # `load_comments()` prefere a Gold `governor_sentiment`; o acessor novo é
    # explícito e só olha a Silver, mesmo com a Gold presente.
    write_deltalake(
        str(tmp_path / "gold" / "governor_sentiment"),
        pd.DataFrame({"id_comment": ["gold"]}),
        mode="overwrite",
    )
    write_deltalake(
        str(tmp_path / "silver" / "comments_clean"),
        pd.DataFrame({"id_comment": ["silver"]}),
        mode="overwrite",
    )
    repo = _repo_tres_camadas(tmp_path)

    assert list(repo.load_comments()["id_comment"]) == ["gold"]
    assert list(repo.load_silver_comments()["id_comment"]) == ["silver"]


@pytest.mark.parametrize(
    "acessor",
    ["load_bronze_profiles", "load_bronze_posts", "load_bronze_reels", "load_bronze_ugc_mentions"],
)
def test_load_bronze_sem_bronze_dir_levanta_value_error(tmp_path, acessor):
    repo = DeltaRepository(gold_dir=tmp_path / "gold", silver_dir=tmp_path / "silver")

    with pytest.raises(ValueError, match="bronze_dir"):
        getattr(repo, acessor)()


def test_load_bronze_tabela_inexistente_levanta_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError, match="instagram_posts"):
        _repo_tres_camadas(tmp_path).load_bronze_posts()


def test_load_bronze_respeita_as_of_version(tmp_path):
    caminho = str(tmp_path / "bronze" / "instagram_profiles")
    write_deltalake(caminho, pd.DataFrame({"id": ["v0"]}), mode="overwrite")
    write_deltalake(caminho, pd.DataFrame({"id": ["v1"]}), mode="overwrite")

    atual = _repo_tres_camadas(tmp_path).load_bronze_profiles()
    antigo = DeltaRepository(
        gold_dir=tmp_path / "gold", bronze_dir=tmp_path / "bronze", as_of_version=0
    ).load_bronze_profiles()

    assert list(atual["id"]) == ["v1"]
    assert list(antigo["id"]) == ["v0"]


def test_bronze_dir_em_uri_s3_nao_corrompe_a_uri(monkeypatch):
    captured = {}

    class FakeDeltaTable:
        def __init__(self, path, storage_options=None):
            captured["path"] = path

        def to_pandas(self):
            return pd.DataFrame({"id": ["1"]})

    monkeypatch.setattr(delta_repository, "DeltaTable", FakeDeltaTable)

    DeltaRepository(gold_dir="s3://b/gold", bronze_dir="s3://b/bronze").load_bronze_reels()

    assert captured["path"] == "s3://b/bronze/instagram_reels"
