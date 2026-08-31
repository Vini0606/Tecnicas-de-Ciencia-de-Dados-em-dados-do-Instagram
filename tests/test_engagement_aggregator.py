import pandas as pd

from src.delta_io import conform_to_schema
from src.features.gold.engagement_aggregator import EngagementAggregator
from src.schemas_delta import GOLD_ENGAGEMENT_SCHEMA


def test_write_repassa_mode_para_write_delta(monkeypatch):
    """A tabela de histórico (ADR 0016) depende de `write` repassar `mode`
    para `write_delta` -- sem isso, toda escrita seria sempre overwrite,
    e a tabela _history nunca acumularia mais de uma linha por run."""
    captured = {}

    def fake_write_delta(path, df, schema, mode="overwrite"):
        captured["path"] = path
        captured["mode"] = mode

    monkeypatch.setattr(
        "src.features.gold.engagement_aggregator.write_delta", fake_write_delta
    )

    EngagementAggregator().write(pd.DataFrame(), "some/path", mode="append")

    assert captured["mode"] == "append"


def _perfis():
    return pd.DataFrame(
        {
            "id": ["1", "2"],
            "username": ["ativo", "sem_posts"],
            "fullName": ["Perfil Ativo", "Perfil Sem Posts"],
            "inputUrl": ["https://instagram.com/ativo", "https://instagram.com/sem_posts"],
            "followersCount": pd.array([1000, 500], dtype="int32"),
            "followsCount": pd.array([10, 20], dtype="int32"),
            "postsCount": pd.array([5, 0], dtype="int32"),
            "verified": [True, True],
            "private": [False, False],
            "isBusinessAccount": [False, False],
            "businessCategoryName": ["Politician", "Politician"],
            "_ingested_at": pd.to_datetime(["2026-05-01", "2026-05-01"], utc=True),
            "_run_id": ["r1", "r1"],
            "_source_layer": ["bronze", "bronze"],
        }
    )


def _publicacoes():
    # Apenas o perfil "1" tem publicações; o perfil "2" fica sem match no merge.
    return pd.DataFrame(
        {
            "id": ["p1", "p2"],
            "ownerId": ["1", "1"],
            "ownerUsername": ["ativo", "ativo"],
            "commentsCount": [10, 20],
            "likesCount": [100, 200],
            "data_hora": pd.to_datetime(["2026-05-01", "2026-05-03"]),
            "Tipo": ["FEED", "FEED"],
        }
    )


def test_perfil_sem_publicacoes_nao_recebe_recencia_maxima():
    """
    Ausência de publicações não pode ser lida como 'postou agora'. Antes da
    correção, o maxData nulo virava 0 dias e produzia RECENCIA = 1.0, o valor
    máximo possível.
    """
    df = EngagementAggregator().aggregate(_perfis(), _publicacoes(), pd.DataFrame(), "r1")

    sem_posts = df.loc[df["username"] == "sem_posts"].iloc[0]
    assert sem_posts["RECENCIA"] == 0.0
    assert sem_posts["TOTAL ENGAJAMENTO"] == 0
    assert sem_posts["count"] == 0


def test_agregado_conforma_ao_contrato_gold():
    """
    O merge é left e o schema Gold declara os agregados como não-anuláveis:
    o perfil sem publicações precisa chegar preenchido com zero, não NaN.
    """
    df = EngagementAggregator().aggregate(_perfis(), _publicacoes(), pd.DataFrame(), "r1")
    table = conform_to_schema(df, GOLD_ENGAGEMENT_SCHEMA)
    assert table.num_rows == 2


def test_engajamento_percentual_nao_divide_por_zero():
    perfis = _perfis()
    perfis["followersCount"] = pd.array([0, 0], dtype="int32")

    df = EngagementAggregator().aggregate(perfis, _publicacoes(), pd.DataFrame(), "r1")

    assert (df["% ENGAJAMENTO"] == 0.0).all()
    assert df["% ENGAJAMENTO"].notna().all()


def test_colunas_de_perfil_sobrevivem_ate_a_gold():
    """Os dashboards leem followsCount e postsCount da tabela Gold."""
    df = EngagementAggregator().aggregate(_perfis(), _publicacoes(), pd.DataFrame(), "r1")
    table = conform_to_schema(df, GOLD_ENGAGEMENT_SCHEMA)
    assert {"followsCount", "postsCount"} <= set(table.column_names)
