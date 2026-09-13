"""Testes da Tela 4 ("Comparar perfis", ADR 0021 / issue #115).

Só a lógica pura de `dashboard/screens/comparar.py` é testada aqui (rename da
coluna de cluster, grupo/par do governador, barras comparativas, seleção do
par de destaque, frase/nível de decisão) -- nunca a renderização Streamlit em
si, mesmo padrão de `tests/test_dashboard_screens_radar.py`/`funil.py`
(issues #113/#114).

Este arquivo também porta os testes equivalentes de `_peer_urls`/
`_pct_diff_vs_peers` que existiam indiretamente em `tests/test_recommendations.py`
(via `check_frequency_below_cluster_peers`/`check_shorter_or_longer_reels_than_peers`)
-- ver Cutover da issue #115: `src/dashboard/recommendations.py` e
`tests/test_recommendations.py` foram apagados depois de portar `_peer_urls`
e `_pct_diff_vs_peers` para dentro deste módulo.
"""

import pandas as pd
import pytest

from dashboard.screens import comparar

GOV_A = "https://www.instagram.com/governador_a/"
GOV_B = "https://www.instagram.com/governador_b/"
GOV_C = "https://www.instagram.com/governador_c/"
GOV_D = "https://www.instagram.com/governador_d/"


# ---------------------------------------------------------------------------
# _carregar_cluster_perfil -- rename cluster_label -> cluster_perfil_engajamento
# (issue #115, docstring do módulo, decisão 1).
# ---------------------------------------------------------------------------


def test_carregar_cluster_perfil_renomeia_cluster_label():
    df_raw = pd.DataFrame({"inputUrl": [GOV_A, GOV_B], "cluster_label": [0, 1]})
    resultado = comparar._carregar_cluster_perfil(df_raw)
    assert list(resultado.columns) == ["inputUrl", "cluster_perfil_engajamento"]
    assert resultado["cluster_perfil_engajamento"].tolist() == [0, 1]


def test_carregar_cluster_perfil_vazio_sem_cluster_label():
    df_raw = pd.DataFrame({"inputUrl": [GOV_A]})
    resultado = comparar._carregar_cluster_perfil(df_raw)
    assert resultado.empty
    assert list(resultado.columns) == ["inputUrl", "cluster_perfil_engajamento"]


def test_carregar_cluster_perfil_dataframe_vazio():
    resultado = comparar._carregar_cluster_perfil(pd.DataFrame())
    assert resultado.empty


# ---------------------------------------------------------------------------
# _cluster_do_governador -- estado vazio (issue #115, user story 5): NaN ou
# ausência de linha são o MESMO caso "sem grupo atribuído", nunca exceção.
# ---------------------------------------------------------------------------


def _df_cluster_perfil():
    return pd.DataFrame(
        {
            "inputUrl": [GOV_A, GOV_B, GOV_C, GOV_D],
            "cluster_perfil_engajamento": [0, 0, 1, float("nan")],
        }
    )


def test_cluster_do_governador_retorna_id_quando_atribuido():
    assert comparar._cluster_do_governador(_df_cluster_perfil(), GOV_A) == 0


def test_cluster_do_governador_none_quando_nan():
    assert comparar._cluster_do_governador(_df_cluster_perfil(), GOV_D) is None


def test_cluster_do_governador_none_quando_sem_linha_correspondente():
    assert (
        comparar._cluster_do_governador(_df_cluster_perfil(), "https://www.instagram.com/nao_existe/")
        is None
    )


def test_cluster_do_governador_none_com_dataframe_vazio():
    assert comparar._cluster_do_governador(pd.DataFrame(), GOV_A) is None


# ---------------------------------------------------------------------------
# _nome_grupo -- nunca o id numérico bruto (issue #115, user story 1).
# ---------------------------------------------------------------------------


def test_nome_grupo_mapeia_ids_curados():
    assert comparar._nome_grupo(-1) == "Casos atípicos / virais"
    assert comparar._nome_grupo(0) == "Alta frequência, engajamento mais baixo"
    assert comparar._nome_grupo(1) == "Alto engajamento, baixa frequência"


def test_nome_grupo_none_retorna_padrao():
    assert comparar._nome_grupo(None) == comparar._NOME_GRUPO_PADRAO


def test_nome_grupo_id_nao_curado_retorna_padrao():
    assert comparar._nome_grupo(99) == comparar._NOME_GRUPO_PADRAO


def test_nome_grupo_nunca_expoe_id_bruto():
    for cluster_id in (-1, 0, 1):
        nome = comparar._nome_grupo(cluster_id)
        assert str(cluster_id) not in nome


# ---------------------------------------------------------------------------
# _peer_urls -- PORTADO de src/dashboard/recommendations.py::_peer_urls (ver
# Cutover da issue #115). Testes equivalentes aos que existiam indiretamente
# em tests/test_recommendations.py.
# ---------------------------------------------------------------------------


def test_peer_urls_retorna_pares_do_mesmo_cluster_excluindo_proprio():
    df = pd.DataFrame(
        {
            "inputUrl": [GOV_A, GOV_B, GOV_C],
            "cluster_perfil_engajamento": [0, 0, 1],
        }
    )
    pares = comparar._peer_urls(df, GOV_A)
    assert pares == [GOV_B]


def test_peer_urls_none_sem_cluster_atribuido():
    df = pd.DataFrame(
        {
            "inputUrl": [GOV_A, GOV_B],
            "cluster_perfil_engajamento": [float("nan"), 0],
        }
    )
    assert comparar._peer_urls(df, GOV_A) is None


def test_peer_urls_none_sem_pares_no_cluster():
    df = pd.DataFrame(
        {
            "inputUrl": [GOV_A, GOV_B],
            "cluster_perfil_engajamento": [0, 1],
        }
    )
    assert comparar._peer_urls(df, GOV_A) is None


def test_peer_urls_none_com_dataframe_vazio():
    assert comparar._peer_urls(pd.DataFrame(), GOV_A) is None


# ---------------------------------------------------------------------------
# _pct_diff_vs_peers -- PORTADO de
# src/dashboard/recommendations.py::_pct_diff_vs_peers.
# ---------------------------------------------------------------------------


def test_pct_diff_vs_peers_positivo_quando_proprio_maior():
    diff = comparar._pct_diff_vs_peers(2.0, pd.Series([1.0, 1.0]))
    assert diff == 100.0


def test_pct_diff_vs_peers_negativo_quando_proprio_menor():
    diff = comparar._pct_diff_vs_peers(0.5, pd.Series([1.0, 1.0]))
    assert diff == -50.0


def test_pct_diff_vs_peers_none_sem_pares_validos():
    assert comparar._pct_diff_vs_peers(1.0, pd.Series([float("nan"), float("nan")])) is None


def test_pct_diff_vs_peers_none_com_valor_proprio_nan():
    assert comparar._pct_diff_vs_peers(float("nan"), pd.Series([1.0])) is None


def test_pct_diff_vs_peers_none_com_media_pares_zero_ou_negativa():
    assert comparar._pct_diff_vs_peers(1.0, pd.Series([0.0, 0.0])) is None


# ---------------------------------------------------------------------------
# _calcular_barra_comparativa / _montar_barras_comparativas -- issue #115,
# Testing Decisions: função pura de barra comparativa, testada com Series
# sintética.
# ---------------------------------------------------------------------------


def test_calcular_barra_comparativa_acima_da_media():
    barra = comparar._calcular_barra_comparativa(
        "alcance_proxy", "Alcance", "pct", 0.8, pd.Series([0.5, 0.5])
    )
    assert barra["rotulo_vs_pares"] == "acima da média dos pares"
    assert barra["media_pares"] == 0.5
    assert barra["diff_pct"] == pytest.approx(60.0)


def test_calcular_barra_comparativa_abaixo_da_media():
    barra = comparar._calcular_barra_comparativa(
        "alcance_proxy", "Alcance", "pct", 0.2, pd.Series([0.5, 0.5])
    )
    assert barra["rotulo_vs_pares"] == "abaixo da média dos pares"


def test_calcular_barra_comparativa_na_media():
    barra = comparar._calcular_barra_comparativa(
        "frequencia", "Frequência", "num", 1.0, pd.Series([1.0, 1.0])
    )
    assert barra["rotulo_vs_pares"] == "na média dos pares"
    assert barra["diff_pct"] == 0.0


def test_calcular_barra_comparativa_sem_pares_validos():
    barra = comparar._calcular_barra_comparativa(
        "frequencia", "Frequência", "num", 1.0, pd.Series(dtype=float)
    )
    assert barra["media_pares"] is None
    assert barra["diff_pct"] is None
    assert barra["rotulo_vs_pares"] == "sem pares suficientes para comparar"


def test_montar_barras_comparativas_gera_uma_barra_por_metrica():
    valores_proprio = {"alcance_proxy": 0.6, "pct_positivo": 0.7, "frequencia": 2.0}
    valores_pares = {
        "alcance_proxy": pd.Series([0.5]),
        "pct_positivo": pd.Series([0.6]),
        "frequencia": pd.Series([2.0]),
    }
    barras = comparar._montar_barras_comparativas(valores_proprio, valores_pares)
    assert [b["chave"] for b in barras] == ["alcance_proxy", "pct_positivo", "frequencia"]


# ---------------------------------------------------------------------------
# _selecionar_par_destaque -- issue #115, user story 3 / Testing Decisions:
# função pura de seleção do par de destaque (maior diferença positiva numa
# métrica).
# ---------------------------------------------------------------------------


def _df_pares_metricas():
    return pd.DataFrame(
        {
            "inputUrl": [GOV_B, GOV_C],
            "nome": ["Gov. B", "Gov. C"],
            "alcance_proxy": [0.5, 0.5],
            "pct_positivo": [0.55, 0.85],
            "frequencia": [2.0, 2.0],
        }
    )


def test_selecionar_par_destaque_escolhe_maior_diferenca_positiva():
    valores_proprio = {"alcance_proxy": 0.5, "pct_positivo": 0.5, "frequencia": 2.0}
    destaque = comparar._selecionar_par_destaque(_df_pares_metricas(), valores_proprio)
    assert destaque is not None
    assert destaque["nome"] == "Gov. C"
    assert destaque["metrica"] == "pct_positivo"
    assert destaque["valor_par"] == 0.85


def test_selecionar_par_destaque_none_sem_pares():
    valores_proprio = {"alcance_proxy": 0.5, "pct_positivo": 0.5, "frequencia": 2.0}
    assert comparar._selecionar_par_destaque(pd.DataFrame(), valores_proprio) is None


def test_selecionar_par_destaque_none_quando_nenhum_par_supera_o_proprio():
    df_pares = pd.DataFrame(
        {
            "inputUrl": [GOV_B],
            "nome": ["Gov. B"],
            "alcance_proxy": [0.1],
            "pct_positivo": [0.1],
            "frequencia": [0.5],
        }
    )
    valores_proprio = {"alcance_proxy": 0.9, "pct_positivo": 0.9, "frequencia": 5.0}
    assert comparar._selecionar_par_destaque(df_pares, valores_proprio) is None


def test_selecionar_par_destaque_ignora_metrica_propria_ausente():
    df_pares = pd.DataFrame(
        {
            "inputUrl": [GOV_B],
            "nome": ["Gov. B"],
            "alcance_proxy": [0.9],
            "pct_positivo": [float("nan")],
            "frequencia": [0.1],
        }
    )
    valores_proprio = {"alcance_proxy": float("nan"), "pct_positivo": 0.5, "frequencia": 5.0}
    # alcance_proxy do próprio é NaN (ignorado); pct_positivo do par é NaN (ignorado);
    # frequencia: par (0.1) não supera o próprio (5.0) -- resultado é None.
    assert comparar._selecionar_par_destaque(df_pares, valores_proprio) is None


def test_frase_destaque_com_par():
    destaque = {
        "nome": "Gov. C",
        "rotulo_metrica": "% positivo",
        "tipo": "pct",
        "valor_par": 0.85,
    }
    frase = comparar._frase_destaque(destaque)
    assert "Gov. C" in frase
    assert "85.0%" in frase


def test_frase_destaque_none():
    frase = comparar._frase_destaque(None)
    assert "Nenhum par" in frase


# ---------------------------------------------------------------------------
# _nivel_decisao / _frase_decisao
# ---------------------------------------------------------------------------


def test_nivel_decisao_good_quando_acima_dos_pares():
    barras = [comparar._calcular_barra_comparativa("m", "Métrica", "pct", 0.9, pd.Series([0.5]))]
    assert comparar._nivel_decisao(barras) == "good"


def test_nivel_decisao_warn_quando_abaixo_dos_pares():
    barras = [comparar._calcular_barra_comparativa("m", "Métrica", "pct", 0.1, pd.Series([0.5]))]
    assert comparar._nivel_decisao(barras) == "warn"


def test_nivel_decisao_info_quando_na_media_ou_sem_dado():
    barras = [comparar._calcular_barra_comparativa("m", "Métrica", "num", 1.0, pd.Series([1.0]))]
    assert comparar._nivel_decisao(barras) == "info"
    barras_vazias = [
        comparar._calcular_barra_comparativa("m", "Métrica", "num", 1.0, pd.Series(dtype=float))
    ]
    assert comparar._nivel_decisao(barras_vazias) == "info"


def test_frase_decisao_menciona_nome_do_grupo():
    barras = [comparar._calcular_barra_comparativa("m", "Métrica", "pct", 0.9, pd.Series([0.5]))]
    frase = comparar._frase_decisao("Alto engajamento, baixa frequência", barras)
    assert "Alto engajamento, baixa frequência" in frase
    assert "acima da média dos pares" in frase


def test_frase_decisao_sem_pares_com_dado_valido():
    barras = [
        comparar._calcular_barra_comparativa("m", "Métrica", "num", 1.0, pd.Series(dtype=float))
    ]
    frase = comparar._frase_decisao("Grupo X", barras)
    assert "ainda não há pares" in frase


# ---------------------------------------------------------------------------
# _montar_metricas_por_governador -- junta engagement/sentimento/metadata por
# inputUrl normalizado.
# ---------------------------------------------------------------------------


def test_montar_metricas_por_governador_junta_as_3_fontes():
    df_engagement = pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/gov_a", "https://www.instagram.com/gov_b/"],
            "% ENGAJAMENTO": [0.6, 0.4],
            "FREQUENCIA": [2.0, 3.0],
        }
    )
    df_sentiment = pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/gov_a/?hl=en"] * 2
            + ["https://www.instagram.com/gov_b"] * 2,
            "sentiment_label": ["positive", "negative", "positive", "positive"],
        }
    )
    df_metadata = pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/gov_a/", "https://www.instagram.com/gov_b/"],
            "nome": ["Governador A", "Governador B"],
        }
    )
    resultado = comparar._montar_metricas_por_governador(df_engagement, df_sentiment, df_metadata)
    resultado = resultado.set_index("nome")
    assert resultado.loc["Governador A", "pct_positivo"] == 0.5
    assert resultado.loc["Governador B", "pct_positivo"] == 1.0
    assert resultado.loc["Governador A", "alcance_proxy"] == 0.6
    assert resultado.loc["Governador B", "frequencia"] == 3.0


def test_montar_metricas_por_governador_vazio_sem_engagement():
    resultado = comparar._montar_metricas_por_governador(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    assert resultado.empty
    assert list(resultado.columns) == ["inputUrl", "nome", "alcance_proxy", "pct_positivo", "frequencia"]


def test_montar_metricas_por_governador_sem_sentimento_nao_quebra():
    df_engagement = pd.DataFrame(
        {"inputUrl": ["https://www.instagram.com/gov_a/"], "% ENGAJAMENTO": [0.5], "FREQUENCIA": [1.0]}
    )
    resultado = comparar._montar_metricas_por_governador(df_engagement, pd.DataFrame(), pd.DataFrame())
    assert resultado["pct_positivo"].isna().all()
    assert resultado["nome"].iloc[0] == "https://www.instagram.com/gov_a/"
