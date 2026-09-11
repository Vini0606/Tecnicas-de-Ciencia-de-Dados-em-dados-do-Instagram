"""
Testes de `src/modeling/growth_history.py` (ADR 0020, Ficha 7 / issue #92).

Seams testados (funções puras, sem I/O):
- `aggregate_monthly`: reduz uma linha por execução a uma linha por
  perfil por mês.
- `compute_cmgr`: fórmula de crescimento mensal composto sobre a série
  mensal já agregada.
- `positive_share_monthly`: share de sentimento positivo por perfil por
  mês, a partir do histórico de sentimento.
- `compute_retention`: taxa média de retenção período-a-período sobre a
  série mensal já agregada.
- `compute_growth_metrics`: combinação de CMGR + retenção numa linha por
  perfil, incluindo o sinalizador `ilustrativo`/`nota` consumido pelo
  dashboard/TCC (issue #92, Testing Decision 3).
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.modeling.growth_history import (
    MIN_PERIODS_CONFIAVEL,
    aggregate_monthly,
    compute_cmgr,
    compute_growth_metrics,
    compute_retention,
    positive_share_monthly,
)


# ---------------------------------------------------------------------------
# aggregate_monthly
# ---------------------------------------------------------------------------


def test_aggregate_monthly_reduz_varias_execucoes_do_mesmo_mes_a_uma_linha():
    df = pd.DataFrame(
        {
            "inputUrl": ["gov_a", "gov_a", "gov_a"],
            "_generated_at": [
                "2026-01-05T00:00:00Z",
                "2026-01-20T00:00:00Z",
                "2026-02-01T00:00:00Z",
            ],
            "followersCount": [100, 110, 200],
        }
    )

    resultado = aggregate_monthly(df, value_col="followersCount", agg="last")

    assert list(resultado["followersCount"]) == [110, 200]
    assert resultado["inputUrl"].tolist() == ["gov_a", "gov_a"]


def test_aggregate_monthly_com_historico_vazio_nao_quebra():
    df = pd.DataFrame(columns=["inputUrl", "_generated_at", "followersCount"])

    resultado = aggregate_monthly(df, value_col="followersCount")

    assert resultado.empty


# ---------------------------------------------------------------------------
# compute_cmgr
# ---------------------------------------------------------------------------


def _serie_mensal(valores: list[float], grupo: str = "gov_a") -> pd.DataFrame:
    periodos = pd.period_range("2026-01", periods=len(valores), freq="M")
    return pd.DataFrame(
        {"inputUrl": [grupo] * len(valores), "periodo": periodos, "valor": valores}
    )


def test_compute_cmgr_sobre_serie_sintetica_conhecida():
    # Valor inicial 100, valor final 133.1, 3 meses de diferença (jan -> abr):
    # CMGR = (133.1/100)**(1/3) - 1 = 0.10 (10% ao mês), por construção.
    df_mensal = _serie_mensal([100.0, 110.0, 121.0, 133.1])

    resultado = compute_cmgr(df_mensal, value_col="valor")

    assert len(resultado) == 1
    linha = resultado.iloc[0]
    assert linha["n_periodos"] == 4
    assert math.isclose(linha["cmgr"], 0.10, rel_tol=1e-9, abs_tol=1e-9)
    assert linha["motivo"] is None


def test_compute_cmgr_com_uma_unica_execucao_retorna_nan_sem_erro():
    df_mensal = _serie_mensal([100.0])

    resultado = compute_cmgr(df_mensal, value_col="valor")

    linha = resultado.iloc[0]
    assert linha["n_periodos"] == 1
    assert math.isnan(linha["cmgr"])
    assert linha["motivo"] == "historico_insuficiente"
    assert bool(linha["confiavel"]) is False


def test_compute_cmgr_com_valor_inicial_zero_nao_gera_infinito_ou_erro():
    df_mensal = _serie_mensal([0.0, 50.0])

    resultado = compute_cmgr(df_mensal, value_col="valor")

    linha = resultado.iloc[0]
    assert math.isnan(linha["cmgr"])
    assert linha["motivo"] == "valor_inicial_invalido"


def test_compute_cmgr_sinaliza_ilustrativo_com_poucas_execucoes_acumuladas():
    # 2 execuções é o mínimo para *calcular* CMGR, mas está abaixo do
    # limiar de confiabilidade (MIN_PERIODS_CONFIAVEL) -- deve ser
    # calculável, mas explicitamente marcado como não confiável/ilustrativo.
    assert MIN_PERIODS_CONFIAVEL > 2
    df_mensal = _serie_mensal([100.0, 121.0])

    resultado = compute_cmgr(df_mensal, value_col="valor")

    linha = resultado.iloc[0]
    assert not math.isnan(linha["cmgr"])
    assert bool(linha["confiavel"]) is False


def test_compute_cmgr_confiavel_quando_atinge_o_limiar_de_execucoes():
    valores = [100.0 * (1.1**i) for i in range(MIN_PERIODS_CONFIAVEL)]
    df_mensal = _serie_mensal(valores)

    resultado = compute_cmgr(df_mensal, value_col="valor")

    linha = resultado.iloc[0]
    assert linha["n_periodos"] == MIN_PERIODS_CONFIAVEL
    assert bool(linha["confiavel"]) is True


def test_compute_cmgr_calcula_por_grupo_independentemente():
    df_mensal = pd.concat(
        [_serie_mensal([100.0, 121.0], grupo="gov_a"), _serie_mensal([100.0, 100.0], grupo="gov_b")],
        ignore_index=True,
    )

    resultado = compute_cmgr(df_mensal, value_col="valor").set_index("inputUrl")

    assert resultado.loc["gov_a", "cmgr"] > 0
    assert math.isclose(resultado.loc["gov_b", "cmgr"], 0.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# positive_share_monthly
# ---------------------------------------------------------------------------


def test_positive_share_monthly_calcula_proporcao_de_positivos_por_mes():
    df = pd.DataFrame(
        {
            "inputUrl": ["gov_a"] * 4,
            "_generated_at": ["2026-01-01"] * 2 + ["2026-02-01"] * 2,
            "sentiment_label": ["positive", "negative", "positive", "positive"],
        }
    )

    resultado = positive_share_monthly(df)

    resultado = resultado.set_index(resultado["periodo"].astype(str))
    assert math.isclose(resultado.loc["2026-01", "positive_share"], 0.5)
    assert math.isclose(resultado.loc["2026-02", "positive_share"], 1.0)


# ---------------------------------------------------------------------------
# compute_retention
# ---------------------------------------------------------------------------


def test_compute_retention_sobre_serie_sintetica_conhecida():
    # 1.0 -> 0.8 (reteve 80%) -> 0.8 (reteve 100% do mês anterior):
    # média de retenção = (0.8 + 1.0) / 2 = 0.9
    df_mensal = _serie_mensal([1.0, 0.8, 0.8])

    resultado = compute_retention(df_mensal, value_col="valor")

    linha = resultado.iloc[0]
    assert math.isclose(linha["retencao_media"], 0.9, rel_tol=1e-9)
    assert linha["n_pares_validos"] == 2


def test_compute_retention_com_uma_unica_execucao_retorna_nan_sem_erro():
    df_mensal = _serie_mensal([1.0])

    resultado = compute_retention(df_mensal, value_col="valor")

    linha = resultado.iloc[0]
    assert math.isnan(linha["retencao_media"])
    assert linha["motivo"] == "historico_insuficiente"
    assert bool(linha["confiavel"]) is False


def test_compute_retention_ignora_pares_com_valor_anterior_zero():
    df_mensal = _serie_mensal([0.0, 0.5, 1.0])

    resultado = compute_retention(df_mensal, value_col="valor")

    linha = resultado.iloc[0]
    # Só o par (0.5 -> 1.0) é válido; (0.0 -> 0.5) é ignorado (razão indefinida).
    assert linha["n_pares_validos"] == 1
    assert math.isclose(linha["retencao_media"], 1.0)


def test_compute_retention_capa_crescimento_em_100_por_cento():
    # Crescimento não deve inflar a "retenção" acima de 1.0 -- retenção mede
    # o que foi mantido do período anterior, não o quanto cresceu.
    df_mensal = _serie_mensal([1.0, 3.0])

    resultado = compute_retention(df_mensal, value_col="valor")

    linha = resultado.iloc[0]
    assert linha["retencao_media"] == 1.0


def test_compute_retention_sinaliza_ilustrativo_com_poucas_execucoes_acumuladas():
    df_mensal = _serie_mensal([1.0, 0.9])

    resultado = compute_retention(df_mensal, value_col="valor")

    linha = resultado.iloc[0]
    assert not math.isnan(linha["retencao_media"])
    assert bool(linha["confiavel"]) is False


# ---------------------------------------------------------------------------
# compute_growth_metrics (combinador -- Testing Decision 3 da issue #92: o
# sinalizador de confiabilidade precisa ser testado no formato que o
# dashboard/TCC efetivamente consomem, não só nas funções internas)
# ---------------------------------------------------------------------------


def _engagement_history(linhas: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(linhas, columns=["inputUrl", "_generated_at", "followersCount"])


def _sentiment_history(linhas: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(linhas, columns=["inputUrl", "_generated_at", "sentiment_label"])


def _meses_2026(n: int) -> list[str]:
    return [f"2026-{mes:02d}-01" for mes in range(1, n + 1)]


def test_compute_growth_metrics_marca_ilustrativo_com_poucas_execucoes():
    meses = _meses_2026(2)  # abaixo de MIN_PERIODS_CONFIAVEL
    df_engagement = _engagement_history(
        [("gov_a", mes, 100.0 * (1.1**i)) for i, mes in enumerate(meses)]
    )
    df_sentiment = _sentiment_history([("gov_a", mes, "positive") for mes in meses])

    resultado = compute_growth_metrics(df_engagement, df_sentiment).set_index("inputUrl")

    linha = resultado.loc["gov_a"]
    assert bool(linha["ilustrativo"]) is True
    assert "ilustrativos" in linha["nota"]


def test_compute_growth_metrics_marca_confiavel_ao_atingir_o_limiar_nas_duas_metricas():
    meses = _meses_2026(MIN_PERIODS_CONFIAVEL)
    df_engagement = _engagement_history(
        [("gov_a", mes, 100.0 * (1.1**i)) for i, mes in enumerate(meses)]
    )
    df_sentiment = _sentiment_history([("gov_a", mes, "positive") for mes in meses])

    resultado = compute_growth_metrics(df_engagement, df_sentiment).set_index("inputUrl")

    linha = resultado.loc["gov_a"]
    assert bool(linha["cmgr_confiavel"]) is True
    assert bool(linha["retencao_confiavel"]) is True
    assert bool(linha["ilustrativo"]) is False
    # `nota` reflete o estado real -- não é o mesmo texto fixo do caso
    # ilustrativo (spec: a ressalva precisa acompanhar o sinalizador, não
    # ser uma string estática independente de `ilustrativo`).
    assert "ilustrativos" not in linha["nota"]
    assert "confiaveis" in linha["nota"]


def test_compute_growth_metrics_perfil_presente_so_em_uma_das_tabelas_nao_quebra():
    # gov_c só aparece em governor_engagement_history -- plausível quando
    # governor_sentiment_history ainda não acumulou nenhuma execução para
    # aquele perfil. O merge outer não pode deixar NaN em colunas
    # `nullable=False` do Gold (cmgr_n_periodos/retencao_n_periodos/
    # retencao_n_pares_validos).
    meses = _meses_2026(MIN_PERIODS_CONFIAVEL)
    df_engagement = _engagement_history(
        [("gov_c", mes, 100.0 * (1.1**i)) for i, mes in enumerate(meses)]
    )
    df_sentiment = _sentiment_history([])

    resultado = compute_growth_metrics(df_engagement, df_sentiment).set_index("inputUrl")

    linha = resultado.loc["gov_c"]
    assert linha["retencao_n_periodos"] == 0
    assert linha["retencao_n_pares_validos"] == 0
    assert math.isnan(linha["retencao"])
    assert bool(linha["retencao_confiavel"]) is False
    assert bool(linha["ilustrativo"]) is True
    # As colunas de contagem precisam ser inteiras (0), não NaN/float --
    # é isso que caberia em `nullable=False` na escrita Delta.
    assert resultado["retencao_n_periodos"].dtype.kind == "i"
    assert resultado["retencao_n_pares_validos"].dtype.kind == "i"
