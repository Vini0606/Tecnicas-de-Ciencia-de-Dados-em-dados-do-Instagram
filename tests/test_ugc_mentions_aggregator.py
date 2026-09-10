"""Testes de `GovernorUGCAggregator` (ADR 0020, Ficha 8 / issue #93)."""

import pandas as pd
import pytest

from src.delta_io import conform_to_schema
from src.features.gold.ugc_mentions_aggregator import GovernorUGCAggregator
from src.schemas_delta import GOLD_UGC_MENTIONS_SCHEMA


def _silver_row(**overrides) -> dict:
    row = {
        "id": "m1",
        "shortCode": "abc123",
        "type": "Image",
        "caption": "apoio total!",
        "matchTypes": "mentioned",
        "governor_username": "governador_x",
        "authorUsername": "eleitor_1",
        "authorIsVerified": False,
        "isPaidPartnership": False,
        "isAd": False,
        "isAffiliate": False,
        "likesCount": 10,
        "commentsCount": 2,
        "videoPlayCount": pd.NA,
        "data_hora": pd.Timestamp("2026-05-01"),
        "_ingested_at": pd.Timestamp("2026-05-01", tz="UTC"),
        "_run_id": "r1",
        "_source_layer": "bronze",
    }
    row.update(overrides)
    return row


def test_enrich_marca_organico_quando_nenhuma_flag_de_publi():
    df = pd.DataFrame([_silver_row()])
    out = GovernorUGCAggregator().enrich(df, run_id="r1")
    assert bool(out.iloc[0]["is_organic"]) is True


@pytest.mark.parametrize("flag", ["isPaidPartnership", "isAd", "isAffiliate"])
def test_enrich_marca_nao_organico_quando_qualquer_flag_de_publi_verdadeira(flag):
    df = pd.DataFrame([_silver_row(**{flag: True})])
    out = GovernorUGCAggregator().enrich(df, run_id="r1")
    assert bool(out.iloc[0]["is_organic"]) is False


def test_enrich_preenche_run_id_e_generated_at():
    df = pd.DataFrame([_silver_row()])
    out = GovernorUGCAggregator().enrich(df, run_id="r_novo")
    assert out.iloc[0]["_run_id"] == "r_novo"
    assert pd.notna(out.iloc[0]["_generated_at"])


def test_enrich_conforma_ao_contrato_gold():
    df = pd.DataFrame([_silver_row(), _silver_row(id="m2", shortCode="def456", isAd=True)])
    out = GovernorUGCAggregator().enrich(df, run_id="r1")
    table = conform_to_schema(out, GOLD_UGC_MENTIONS_SCHEMA)
    assert table.num_rows == 2


def _gold_df() -> pd.DataFrame:
    """3 posts orgânicos e 1 publi paga para o mesmo governador, 1 post
    orgânico para outro governador -- dataset sintético simulando o
    piloto pequeno descrito na issue."""
    rows = [
        {"governor_username": "governador_x", "is_organic": True, "likesCount": 10, "commentsCount": 2},
        {"governor_username": "governador_x", "is_organic": True, "likesCount": 20, "commentsCount": 4},
        {"governor_username": "governador_x", "is_organic": True, "likesCount": 30, "commentsCount": 6},
        # publi paga com engajamento MUITO maior -- se não for filtrada,
        # infla a média orgânica de forma óbvia no teste abaixo.
        {"governor_username": "governador_x", "is_organic": False, "likesCount": 10000, "commentsCount": 5000},
        {"governor_username": "governador_y", "is_organic": True, "likesCount": 5, "commentsCount": 1},
    ]
    return pd.DataFrame(rows)


def test_aggregate_by_governor_conta_so_organico():
    result = GovernorUGCAggregator().aggregate_by_governor(_gold_df())
    linha_x = result.loc[result["governor_username"] == "governador_x"].iloc[0]
    assert linha_x["count_organic"] == 3
    assert linha_x["count_paid"] == 1


def test_aggregate_by_governor_engajamento_medio_exclui_publi():
    """Teste explícito comparando com/sem o filtro (Testing Decisions da
    issue #93): a média orgânica (10+2 + 20+4 + 30+6)/3 = 24 não pode ser
    puxada pela publi paga (10000+5000)."""
    result = GovernorUGCAggregator().aggregate_by_governor(_gold_df())
    linha_x = result.loc[result["governor_username"] == "governador_x"].iloc[0]
    assert linha_x["avg_engagement_organic"] == pytest.approx(24.0)


def test_filtro_de_publi_muda_o_resultado():
    """Prova que o filtro de is_organic realmente muda o número -- sem ele
    (média sobre TODAS as linhas, orgânicas + publi), o resultado seria
    muito maior."""
    df = _gold_df()
    result_filtrado = GovernorUGCAggregator().aggregate_by_governor(df)
    media_filtrada = result_filtrado.loc[
        result_filtrado["governor_username"] == "governador_x", "avg_engagement_organic"
    ].iloc[0]

    df_sem_filtro = df.copy()
    df_sem_filtro["engajamento"] = df_sem_filtro["likesCount"] + df_sem_filtro["commentsCount"]
    media_sem_filtro = (
        df_sem_filtro.loc[df_sem_filtro["governor_username"] == "governador_x", "engajamento"].mean()
    )

    assert media_filtrada != pytest.approx(media_sem_filtro)
    assert media_filtrada < media_sem_filtro


def test_aggregate_by_governor_nao_expoe_author_username():
    """Privacidade (ADR 0020, Ficha 8): agregado nunca lista autores
    individuais, só contagens/médias por governador."""
    result = GovernorUGCAggregator().aggregate_by_governor(_gold_df())
    assert "authorUsername" not in result.columns


def test_aggregate_by_governor_dataframe_vazio():
    result = GovernorUGCAggregator().aggregate_by_governor(pd.DataFrame())
    assert result.empty


def test_aggregate_by_governor_sem_nenhum_post_organico_nao_quebra():
    """Governador só com publi paga (0 UGC orgânico) não pode gerar NaN nem
    exceção -- precisa cair em 0/0.0, não em linha ausente."""
    df = pd.DataFrame(
        [{"governor_username": "governador_z", "is_organic": False, "likesCount": 100, "commentsCount": 50}]
    )
    result = GovernorUGCAggregator().aggregate_by_governor(df)
    linha = result.loc[result["governor_username"] == "governador_z"].iloc[0]
    assert linha["count_organic"] == 0
    assert linha["avg_engagement_organic"] == 0.0
    assert linha["count_paid"] == 1
