"""Testes da Tela 2 ("O que produzir", ADR 0021 / issue #112).

Só a lógica pura de `dashboard/screens/produzir.py` é testada aqui (selo de
prioridade, mapeamento cluster -> cartão, recomendação principal) -- nunca a
renderização Streamlit em si, mesmo padrão de
`tests/test_dashboard_screens_resumo.py` (issue #111)."""

import inspect

import pandas as pd
import streamlit as st
from deltalake.writer import write_deltalake

from config import settings
from dashboard.core import data
from dashboard.screens import produzir


def _clear_caches():
    st.cache_resource.clear()
    st.cache_data.clear()


def _point_settings_at(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "GOLD_DIR", tmp_path / "gold")
    monkeypatch.setattr(settings, "SILVER_DIR", tmp_path / "silver")
    _clear_caches()


# ---------------------------------------------------------------------------
# _selo_prioridade / _cortes_tercis (selo de prioridade, nunca o score bruto)
# ---------------------------------------------------------------------------


def test_selo_prioridade_alta_quando_score_igual_ao_corte_alta():
    assert (
        produzir._selo_prioridade(0.5, corte_alta=0.5, corte_media=0.2)
        == produzir.SELO_ALTA
    )


def test_selo_prioridade_alta_acima_do_corte():
    assert (
        produzir._selo_prioridade(0.9, corte_alta=0.5, corte_media=0.2)
        == produzir.SELO_ALTA
    )


def test_selo_prioridade_media_entre_os_dois_cortes():
    assert (
        produzir._selo_prioridade(0.3, corte_alta=0.5, corte_media=0.2)
        == produzir.SELO_MEDIA
    )


def test_selo_prioridade_media_no_valor_de_fronteira():
    # score == corte_media entra na banda "média" (inclusivo do lado alto).
    assert (
        produzir._selo_prioridade(0.2, corte_alta=0.5, corte_media=0.2)
        == produzir.SELO_MEDIA
    )


def test_selo_prioridade_cuidado_abaixo_do_corte_media():
    assert (
        produzir._selo_prioridade(0.1, corte_alta=0.5, corte_media=0.2)
        == produzir.SELO_CUIDADO
    )


def test_selo_prioridade_cuidado_para_score_nulo():
    assert (
        produzir._selo_prioridade(None, corte_alta=0.5, corte_media=0.2)
        == produzir.SELO_CUIDADO
    )
    assert (
        produzir._selo_prioridade(float("nan"), corte_alta=0.5, corte_media=0.2)
        == produzir.SELO_CUIDADO
    )


def test_cortes_tercis_calcula_quantis_sobre_todo_o_ranking():
    df = pd.DataFrame({"score": [0.0, 0.3, 0.6, 0.9]})
    corte_alta, corte_media = produzir._cortes_tercis(df)
    assert corte_alta == df["score"].quantile(2 / 3)
    assert corte_media == df["score"].quantile(1 / 3)


def test_cortes_tercis_retorna_zero_para_tabela_vazia():
    assert produzir._cortes_tercis(pd.DataFrame()) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# Fila de pautas (issue #191) -- `content_topic_priority_score` é GLOBAL (sem
# inputUrl); o governador só restringe quais pautas aparecem.
# ---------------------------------------------------------------------------


def _df_pautas_global():
    # 4 pautas com scores bem espalhados para cair em bandas diferentes.
    # Rótulos nos 3 formatos reais: keywords brutas, refinado e degenerado.
    return pd.DataFrame(
        {
            "Topic": [0, 1, 2, 3],
            "Name": [
                "mobiliza, 0001, elmano, queremos",
                "Entregas de obras, obra, entrega",
                "sem assunto definido",
                "saude, hospital",
            ],
            "score": [0.9, 0.6, 0.3, 0.05],
            "n_comentarios": [120, 45, 0, 3],
            "proporcao_sentimento_positivo": [0.8, 0.5, 0.0, 0.2],
        }
    )


def _df_discurso():
    # governor_discourse_topics: reels repetidos, ruido (-1) e transcricao.
    return pd.DataFrame(
        {
            "id_reel": ["a1", "a1", "a2", "a3", "b1", "b2", "b3", "b4"],
            "inputUrl": [_GOV_URL] * 3
            + [_GOV_URL]
            + ["https://www.instagram.com/gov_b/"] * 4,
            "fonte": ["legenda", "legenda", "legenda", "transcricao"]
            + ["legenda", "legenda", "legenda", "legenda"],
            "Topic": [1, 1, 3, 0, 0, 1, -1, 2],
            "Name": ["x"] * 8,
        }
    )


def test_reels_por_pauta_so_legenda_sem_ruido_e_sem_duplicata():
    resultado = produzir._reels_por_pauta(_df_discurso())
    # a1 duplicado vira 1 linha; a3 e transcricao; b3 e ruido (-1).
    assert sorted(resultado["id_reel"]) == ["a1", "a2", "b1", "b2", "b4"]
    assert dict(zip(resultado["id_reel"], resultado["Topic"], strict=True))["a1"] == 1


def test_reels_por_pauta_entrada_vazia_sem_quebrar():
    assert produzir._reels_por_pauta(pd.DataFrame()).empty
    assert produzir._reels_por_pauta(pd.DataFrame({"x": [1]})).empty


def test_pautas_do_governador_so_as_pautas_dos_reels_dele():
    discurso_gov = produzir._filtrar_por_governador(_df_discurso(), _GOV_URL)
    assert produzir._pautas_do_governador(discurso_gov) == {1, 3}


def test_pautas_do_governador_vazio_sem_quebrar():
    assert produzir._pautas_do_governador(pd.DataFrame()) == set()


def test_fila_prioridade_restringe_ao_governador_e_ordena_por_score():
    fila = produzir._fila_prioridade(_df_pautas_global(), pautas_governador={1, 3})

    assert list(fila["Topic"]) == [1, 3]
    assert list(fila["Pauta"]) == ["Entregas de obras", "saude, hospital"]
    # score segue como coluna interna (recomendacao); render() nunca o exibe.
    assert "score" in fila.columns
    assert "Prioridade" in fila.columns


def test_fila_prioridade_selo_vem_dos_tercis_globais_nao_do_governador():
    # Governador so tem as pautas 1 (0.6) e 3 (0.05). Tercis GLOBAIS de
    # [0.9, 0.6, 0.3, 0.05]: alta >= 0.6, media >= 0.3333 -> pauta 1 e Alta
    # mesmo sendo a "melhor" do governador por acaso; pauta 3 e Cuidado.
    fila = produzir._fila_prioridade(_df_pautas_global(), pautas_governador={1, 3})
    assert list(fila["Prioridade"]) == [produzir.SELO_ALTA, produzir.SELO_CUIDADO]


def test_fila_prioridade_propaga_comentarios_e_positivo_globais():
    fila = produzir._fila_prioridade(_df_pautas_global(), pautas_governador={1, 3})
    assert list(fila["n_comentarios"]) == [45, 3]
    assert list(fila["proporcao_sentimento_positivo"]) == [0.5, 0.2]


def test_fila_prioridade_sem_n_comentarios_no_dado_de_entrada_nao_quebra():
    df = _df_pautas_global().drop(columns=["n_comentarios"])
    fila = produzir._fila_prioridade(df, pautas_governador={1, 3})
    assert fila["n_comentarios"].isna().all()


def test_fila_prioridade_pauta_degenerada_continua_na_fila_com_rotulo_amigavel():
    fila = produzir._fila_prioridade(_df_pautas_global(), pautas_governador={2})
    assert list(fila["Pauta"]) == ["sem assunto definido"]


def test_fila_prioridade_vazia_quando_tabela_ausente():
    fila = produzir._fila_prioridade(pd.DataFrame(), pautas_governador={1})
    assert fila.empty
    assert list(fila.columns) == produzir._COLUNAS_FILA


def test_fila_prioridade_vazia_quando_governador_sem_pautas():
    fila = produzir._fila_prioridade(_df_pautas_global(), pautas_governador=set())
    assert fila.empty


def test_fila_prioridade_nao_vaza_pauta_de_outro_governador_com_score_maior():
    fila = produzir._fila_prioridade(_df_pautas_global(), pautas_governador={3})
    assert list(fila["Topic"]) == [3]


def test_estado_fila_distingue_tabela_ausente_sem_pautas_e_ok():
    df = _df_pautas_global()
    fila_ok = produzir._fila_prioridade(df, {1})
    assert (
        produzir._estado_fila(pd.DataFrame(), fila_ok)
        == produzir.ESTADO_FILA_TABELA_AUSENTE
    )
    assert (
        produzir._estado_fila(df, produzir._fila_prioridade(df, set()))
        == produzir.ESTADO_FILA_SEM_PAUTAS
    )
    assert produzir._estado_fila(df, fila_ok) == produzir.ESTADO_FILA_OK


def test_rotulo_exibicao_aceita_bruto_refinado_degenerado_e_nulo():
    assert (
        produzir._rotulo_exibicao("mobiliza, 0001, elmano") == "mobiliza, 0001, elmano"
    )
    assert produzir._rotulo_exibicao("Entregas de obras, obra") == "Entregas de obras"
    assert (
        produzir._rotulo_exibicao("3_Entregas de obras_obra_entrega")
        == "Entregas de obras"
    )
    assert produzir._rotulo_exibicao("2_saude_hospital") == "saude, hospital"
    assert produzir._rotulo_exibicao("1____") == "sem assunto definido"
    assert produzir._rotulo_exibicao(None) == "sem assunto definido"
    assert produzir._rotulo_exibicao(float("nan")) == "sem assunto definido"


def test_rotulo_exibicao_trunca_lista_longa():
    longo = ", ".join(f"palavra{i}" for i in range(30))
    resultado = produzir._rotulo_exibicao(longo)
    assert len(resultado) <= 60
    assert resultado.endswith("…")


# ---------------------------------------------------------------------------
# _clusters_reel_do_governador / _estatisticas_por_grupo
# ---------------------------------------------------------------------------


def _df_clusters_3_puros_mais_ruido():
    return pd.DataFrame(
        {
            "id_reel": ["r1", "r2", "r3", "r4", "r5", "r6", "r7"],
            "ownerUsername": ["gov_a"] * 7,
            # grupo 0: curto (duração baixa, engajamento moderado e estável)
            # grupo 1: longo (duração alta)
            # grupo 2: alto engajamento/variância (vira viral junto do ruído)
            # -1: ruído
            "cluster_label": [0, 0, 1, 1, 2, 2, -1],
            "content_type": ["reel"] * 7,
            "_run_id": ["run1"] * 7,
        }
    )


def _df_reels_para_clusters():
    return pd.DataFrame(
        {
            "id": ["r1", "r2", "r3", "r4", "r5", "r6", "r7"],
            "inputUrl": ["https://www.instagram.com/gov_a/"] * 7,
            "Total de Engajamento": [100, 120, 80, 90, 5000, 200, 3000],
            "videoDuration": [10.0, 12.0, 90.0, 95.0, 15.0, 14.0, 20.0],
        }
    )


def test_clusters_reel_do_governador_filtra_content_type_e_governador():
    merged = produzir._clusters_reel_do_governador(
        _df_clusters_3_puros_mais_ruido(),
        _df_reels_para_clusters(),
        "https://www.instagram.com/gov_a/",
    )
    assert len(merged) == 7
    assert set(merged["cluster_label"]) == {0, 1, 2, -1}


def test_clusters_reel_do_governador_vazio_para_outro_governador():
    merged = produzir._clusters_reel_do_governador(
        _df_clusters_3_puros_mais_ruido(),
        _df_reels_para_clusters(),
        "https://www.instagram.com/outro_gov/",
    )
    assert merged.empty


def test_estatisticas_por_grupo_agrega_por_cluster_label():
    merged = produzir._clusters_reel_do_governador(
        _df_clusters_3_puros_mais_ruido(),
        _df_reels_para_clusters(),
        "https://www.instagram.com/gov_a/",
    )
    estatisticas = produzir._estatisticas_por_grupo(merged)
    linha_grupo1 = estatisticas.set_index("cluster_label").loc[1]
    assert linha_grupo1["duracao_media"] == 92.5
    assert linha_grupo1["n"] == 2


def test_estatisticas_por_grupo_vazio_sem_quebrar():
    estatisticas = produzir._estatisticas_por_grupo(pd.DataFrame())
    assert estatisticas.empty


# ---------------------------------------------------------------------------
# _mapear_grupos_para_cartoes -- nunca "-1" em nenhuma string, nunca cartão
# próprio de ruído
# ---------------------------------------------------------------------------


def test_mapear_grupos_baseline_3_puros_mais_ruido():
    merged = produzir._clusters_reel_do_governador(
        _df_clusters_3_puros_mais_ruido(),
        _df_reels_para_clusters(),
        "https://www.instagram.com/gov_a/",
    )
    estatisticas = produzir._estatisticas_por_grupo(merged)
    cartoes = produzir._mapear_grupos_para_cartoes(estatisticas)

    assert set(cartoes.keys()) == {
        produzir.GRUPO_CURTO,
        produzir.GRUPO_LONGO,
        produzir.GRUPO_VIRAL,
    }
    # Grupo 1 (duração média 92.5) é claramente o mais longo.
    assert cartoes[produzir.GRUPO_LONGO]["n"] == 2
    # Grupo 2 (engajamento 5000/200) + ruído (3000) formam "viral, debatido".
    assert cartoes[produzir.GRUPO_VIRAL]["n"] == 3
    # Grupo 0 sobra para "curto, converte".
    assert cartoes[produzir.GRUPO_CURTO]["n"] == 2


def test_mapear_grupos_nunca_inclui_id_numerico_em_string_nenhuma():
    merged = produzir._clusters_reel_do_governador(
        _df_clusters_3_puros_mais_ruido(),
        _df_reels_para_clusters(),
        "https://www.instagram.com/gov_a/",
    )
    estatisticas = produzir._estatisticas_por_grupo(merged)
    cartoes = produzir._mapear_grupos_para_cartoes(estatisticas)

    for chave, stats in cartoes.items():
        assert "-1" not in chave
        assert chave in produzir._ORDEM_CARTOES
        for valor in stats.values():
            assert "-1" not in str(valor) or isinstance(valor, (int, float))


def test_mapear_grupos_ruido_sozinho_vira_viral_sem_ser_cartao_proprio():
    estatisticas = pd.DataFrame(
        {
            "cluster_label": [-1],
            "n": [3],
            "engajamento_medio": [500.0],
            "engajamento_var": [10.0],
            "duracao_media": [20.0],
        }
    )
    cartoes = produzir._mapear_grupos_para_cartoes(estatisticas)
    assert set(cartoes.keys()) == {produzir.GRUPO_VIRAL}
    assert cartoes[produzir.GRUPO_VIRAL]["n"] == 3


def test_mapear_grupos_um_grupo_puro_absorve_ruido_em_viral():
    estatisticas = pd.DataFrame(
        {
            "cluster_label": [0, -1],
            "n": [5, 2],
            "engajamento_medio": [300.0, 900.0],
            "engajamento_var": [10.0, 5.0],
            "duracao_media": [30.0, 40.0],
        }
    )
    cartoes = produzir._mapear_grupos_para_cartoes(estatisticas)
    assert set(cartoes.keys()) == {produzir.GRUPO_VIRAL}
    assert cartoes[produzir.GRUPO_VIRAL]["n"] == 7


def test_mapear_grupos_dois_puros_sem_cartao_curto():
    # Só 2 grupos puros: um vira "longo" (maior duração), o outro absorve o
    # ruído e vira "viral" -- "curto, converte" não deve aparecer (issue
    # #112 pede documentar a adaptação quando não há 3 grupos puros).
    estatisticas = pd.DataFrame(
        {
            "cluster_label": [0, 1, -1],
            "n": [4, 3, 2],
            "engajamento_medio": [200.0, 150.0, 800.0],
            "engajamento_var": [5.0, 5.0, 5.0],
            "duracao_media": [15.0, 80.0, 20.0],
        }
    )
    cartoes = produzir._mapear_grupos_para_cartoes(estatisticas)
    assert set(cartoes.keys()) == {produzir.GRUPO_LONGO, produzir.GRUPO_VIRAL}
    assert cartoes[produzir.GRUPO_LONGO]["n"] == 3
    assert cartoes[produzir.GRUPO_VIRAL]["n"] == 6


def test_mapear_grupos_quatro_puros_combina_sobra_em_curto():
    estatisticas = pd.DataFrame(
        {
            "cluster_label": [0, 1, 2, 3, -1],
            "n": [2, 2, 2, 2, 1],
            "engajamento_medio": [100.0, 110.0, 900.0, 120.0, 50.0],
            "engajamento_var": [5.0, 5.0, 400.0, 5.0, 5.0],
            "duracao_media": [10.0, 12.0, 15.0, 200.0, 20.0],
        }
    )
    cartoes = produzir._mapear_grupos_para_cartoes(estatisticas)
    assert set(cartoes.keys()) == {
        produzir.GRUPO_CURTO,
        produzir.GRUPO_LONGO,
        produzir.GRUPO_VIRAL,
    }
    # grupo 3 (duração 200) -> longo; grupo 2 (variancia 400) + ruído -> viral;
    # grupos 0 e 1 combinados -> curto (n = 2 + 2 = 4).
    assert cartoes[produzir.GRUPO_LONGO]["n"] == 2
    assert cartoes[produzir.GRUPO_VIRAL]["n"] == 3
    assert cartoes[produzir.GRUPO_CURTO]["n"] == 4


def test_mapear_grupos_vazio_sem_quebrar():
    assert produzir._mapear_grupos_para_cartoes(pd.DataFrame()) == {}


# ---------------------------------------------------------------------------
# _grupo_maior_engajamento -- calculado, nunca hardcoded "curto"
# ---------------------------------------------------------------------------


def test_grupo_maior_engajamento_calcula_o_vencedor_real():
    cartoes = {
        produzir.GRUPO_CURTO: {"n": 5, "engajamento_medio": 100.0},
        produzir.GRUPO_LONGO: {"n": 3, "engajamento_medio": 50.0},
        produzir.GRUPO_VIRAL: {"n": 2, "engajamento_medio": 900.0},
    }
    assert produzir._grupo_maior_engajamento(cartoes) == produzir.GRUPO_VIRAL


def test_grupo_maior_engajamento_nao_hardcoda_curto_quando_curto_perde():
    cartoes = {
        produzir.GRUPO_CURTO: {"n": 5, "engajamento_medio": 10.0},
        produzir.GRUPO_LONGO: {"n": 3, "engajamento_medio": 500.0},
    }
    assert produzir._grupo_maior_engajamento(cartoes) == produzir.GRUPO_LONGO


def test_grupo_maior_engajamento_vazio_retorna_none():
    assert produzir._grupo_maior_engajamento({}) is None


# ---------------------------------------------------------------------------
# _pauta_prioritaria_ajustada / _recomendacao_principal (migradas para pautas)
# ---------------------------------------------------------------------------


def _fila_duas_pautas():
    return pd.DataFrame(
        {
            "Topic": [0, 1],
            "Name": ["muito, coberta", "pouco, coberta"],
            "Pauta": ["muito, coberta", "pouco, coberta"],
            "score": [0.9, 0.5],
            "proporcao_sentimento_positivo": [0.8, 0.6],
            "Prioridade": [produzir.SELO_ALTA, produzir.SELO_MEDIA],
        }
    )


def _discurso_governador(topics):
    return pd.DataFrame(
        {
            "id_reel": [f"r{i}" for i in range(len(topics))],
            "fonte": ["legenda"] * len(topics),
            "Topic": topics,
        }
    )


def test_pauta_prioritaria_ajustada_pula_pauta_muito_coberta():
    # 5 reels na pauta 0, 1 na pauta 1 -> mediana 3; pauta 0 (5) esta acima.
    discurso = _discurso_governador([0, 0, 0, 0, 0, 1])
    resultado = produzir._pauta_prioritaria_ajustada(_fila_duas_pautas(), discurso)
    assert resultado["Pauta"] == "pouco, coberta"


def test_pauta_prioritaria_ajustada_usa_topo_sem_dado_de_discurso():
    resultado = produzir._pauta_prioritaria_ajustada(
        _fila_duas_pautas(), pd.DataFrame()
    )
    assert resultado["Pauta"] == "muito, coberta"


def test_pauta_prioritaria_ajustada_none_com_fila_vazia():
    assert produzir._pauta_prioritaria_ajustada(pd.DataFrame(), pd.DataFrame()) is None


def test_pauta_prioritaria_ajustada_nunca_recomenda_pauta_degenerada():
    fila = _fila_duas_pautas()
    fila.loc[0, ["Name", "Pauta"]] = "sem assunto definido"
    resultado = produzir._pauta_prioritaria_ajustada(fila, pd.DataFrame())
    assert resultado["Topic"] == 1


def test_pauta_prioritaria_ajustada_none_quando_so_ha_degeneradas():
    fila = _fila_duas_pautas().iloc[:1].copy()
    fila["Name"] = "sem assunto definido"
    assert produzir._pauta_prioritaria_ajustada(fila, pd.DataFrame()) is None


def test_recomendacao_principal_combina_pauta_e_formato_calculados():
    cartoes = {
        produzir.GRUPO_CURTO: {"n": 5, "engajamento_medio": 100.0},
        produzir.GRUPO_VIRAL: {"n": 2, "engajamento_medio": 900.0},
    }
    recomendacao = produzir._recomendacao_principal(
        _fila_duas_pautas(), pd.DataFrame(), cartoes
    )
    assert recomendacao == {"pauta": "muito, coberta", "grupo": produzir.GRUPO_VIRAL}


def test_recomendacao_principal_none_sem_cartoes():
    assert (
        produzir._recomendacao_principal(_fila_duas_pautas(), pd.DataFrame(), {})
        is None
    )


def test_recomendacao_principal_none_sem_fila():
    cartoes = {produzir.GRUPO_CURTO: {"n": 5, "engajamento_medio": 100.0}}
    assert (
        produzir._recomendacao_principal(pd.DataFrame(), pd.DataFrame(), cartoes)
        is None
    )


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------


def test_fmt_pct_arredonda_e_nao_mostra_float_bruto():
    assert produzir._fmt_pct(0.71428571) == "71.4%"


def test_fmt_pct_com_none_mostra_placeholder():
    assert produzir._fmt_pct(None) == "—"


def test_fmt_int_br_usa_separador_de_milhar():
    assert produzir._fmt_int_br(12345.6) == "12.346"


# ---------------------------------------------------------------------------
# _filtrar_fila_por_prioridade (ADR 0028 / issue #166) -- filtro de botão
# único sobre a fila já calculada; nunca afeta o cálculo do selo em si.
# ---------------------------------------------------------------------------


def _fila_com_selos():
    return pd.DataFrame(
        {
            "Topic": [0, 1, 2],
            "Name": ["a", "b", "c"],
            "Prioridade": [produzir.SELO_ALTA, produzir.SELO_MEDIA, produzir.SELO_ALTA],
        }
    )


def test_filtrar_fila_por_prioridade_todas_retorna_fila_inteira():
    fila = _fila_com_selos()
    resultado = produzir._filtrar_fila_por_prioridade(fila, produzir.FILTRO_TODAS)
    assert list(resultado["Topic"]) == [0, 1, 2]


def test_filtrar_fila_por_prioridade_none_retorna_fila_inteira():
    fila = _fila_com_selos()
    resultado = produzir._filtrar_fila_por_prioridade(fila, None)
    assert list(resultado["Topic"]) == [0, 1, 2]


def test_filtrar_fila_por_prioridade_filtra_uma_faixa():
    fila = _fila_com_selos()
    resultado = produzir._filtrar_fila_por_prioridade(fila, produzir.SELO_ALTA)
    assert list(resultado["Topic"]) == [0, 2]


def test_filtrar_fila_por_prioridade_faixa_sem_linha_nenhuma_fica_vazia():
    fila = _fila_com_selos()
    resultado = produzir._filtrar_fila_por_prioridade(fila, produzir.SELO_CUIDADO)
    assert resultado.empty


def test_filtrar_fila_por_prioridade_vazia_sem_quebrar():
    resultado = produzir._filtrar_fila_por_prioridade(
        pd.DataFrame(), produzir.SELO_ALTA
    )
    assert resultado.empty


# ---------------------------------------------------------------------------
# _comentarios_da_pauta (popup, issue #191) -- comentarios GLOBAIS dos reels da
# pauta, ligados por id_reel; o Topic do proprio comentario e ignorado.
# ---------------------------------------------------------------------------


def _df_comentarios():
    return pd.DataFrame(
        {
            "id_reel": ["a1", "a1", "a2", "b2", "b4", "zz"],
            # Topic de GRUPO DE COMENTARIOS -- nao deve influenciar o popup.
            "Topic": [9, 9, 9, 9, 9, 9],
            "text": [
                "c_baixo",
                "c_alto",
                "c_medio",
                "c_outro_perfil",
                "c_pauta2",
                "c_sem_pauta",
            ],
            "sentiment_label": [
                "positive",
                "positive",
                "negative",
                "positive",
                "positive",
                "x",
            ],
            "likesCount": [1, 50, 10, 5, 999, 999],
            "repliesCount": [0, 5, 2, 0, 999, 999],
            "ownerUsername": ["u1", "u2", "u3", "u4", "u5", "u6"],
            "timestamp": ["2026-01-01"] * 6,
        }
    )


def test_comentarios_da_pauta_traz_so_comentarios_dos_reels_da_pauta():
    resultado = produzir._comentarios_da_pauta(
        _df_comentarios(), _df_discurso(), topic=1
    )
    # Pauta 1 = reels a1 (Gov A) e b2 (Gov B): global, todos os perfis.
    assert set(resultado["text"]) == {"c_baixo", "c_alto", "c_outro_perfil"}


def test_comentarios_da_pauta_ordena_por_engajamento_e_corta_no_top_n():
    resultado = produzir._comentarios_da_pauta(
        _df_comentarios(), _df_discurso(), 1, top_n=2
    )
    assert list(resultado["text"]) == ["c_alto", "c_outro_perfil"]


def test_comentarios_da_pauta_colunas_exibidas():
    resultado = produzir._comentarios_da_pauta(
        _df_comentarios(), _df_discurso(), topic=1
    )
    assert list(resultado.columns) == produzir._COLUNAS_COMENTARIOS_POPUP


def test_comentarios_da_pauta_sem_comentario_fica_vazia_com_colunas():
    # Pauta 0: so b1 (sem comentarios); a3 e transcricao e fica fora.
    resultado = produzir._comentarios_da_pauta(
        _df_comentarios(), _df_discurso(), topic=0
    )
    assert resultado.empty
    assert list(resultado.columns) == produzir._COLUNAS_COMENTARIOS_POPUP


def test_comentarios_da_pauta_entradas_vazias_sem_quebrar():
    assert produzir._comentarios_da_pauta(pd.DataFrame(), _df_discurso(), 1).empty
    assert produzir._comentarios_da_pauta(_df_comentarios(), pd.DataFrame(), 1).empty
    sem_id = pd.DataFrame({"text": ["a"]})
    assert produzir._comentarios_da_pauta(sem_id, _df_discurso(), 1).empty


def test_comentarios_da_pauta_likes_e_replies_nulos_tratados_como_zero():
    df = pd.DataFrame(
        {
            "id_reel": ["a1", "a1"],
            "text": ["sem_engajamento", "com_engajamento"],
            "likesCount": [None, 3],
            "repliesCount": [None, None],
        }
    )
    resultado = produzir._comentarios_da_pauta(df, _df_discurso(), topic=1)
    assert list(resultado["text"]) == ["com_engajamento", "sem_engajamento"]


def test_comentarios_da_pauta_reel_sem_pauta_de_legenda_fica_de_fora():
    # a3 so tem transcricao (Topic 0) -> nao pertence a pauta 0.
    df = pd.DataFrame(
        {"id_reel": ["a3"], "text": ["x"], "likesCount": [1], "repliesCount": [0]}
    )
    assert produzir._comentarios_da_pauta(df, _df_discurso(), topic=0).empty


# ---------------------------------------------------------------------------
# Destaques (ADR 0026 / issue #154) -- "Melhor post" e "Alto potencial,
# pouco discurso", portados sem mudança de comportamento de resumo.py.
# ---------------------------------------------------------------------------

_GOV_URL = "https://www.instagram.com/gov_a/"


def _df_clusters_conteudo():
    return pd.DataFrame(
        {
            "id_reel": ["r1", "r2", "p1"],
            "ownerUsername": ["gov_a", "gov_a", "gov_a"],
            "cluster_label": [0, 1, 0],
            "content_type": ["reel", "reel", "feed"],
            "_run_id": ["run1", "run1", "run1"],
        }
    )


def _df_reels_conteudo():
    return pd.DataFrame(
        {
            "id": ["r1", "r2", "p1"],
            "inputUrl": [_GOV_URL] * 3,
            "shortCode": ["abc", "xyz", "feed1"],
            "Total de Engajamento": [100, 500, 900],
        }
    )


def test_melhor_post_escolhe_maior_engajamento_entre_reels_do_governador():
    resultado = produzir._melhor_post(
        _df_clusters_conteudo(), _df_reels_conteudo(), _GOV_URL
    )
    assert resultado is not None
    assert resultado["shortCode"] == "xyz"
    assert resultado["total_engajamento"] == 500


def test_melhor_post_retorna_none_quando_tabelas_vazias():
    assert produzir._melhor_post(pd.DataFrame(), pd.DataFrame(), _GOV_URL) is None
    assert (
        produzir._melhor_post(_df_clusters_conteudo(), pd.DataFrame(), _GOV_URL) is None
    )


def test_melhor_post_retorna_none_sem_reel_do_governador():
    resultado = produzir._melhor_post(
        _df_clusters_conteudo(),
        _df_reels_conteudo(),
        "https://www.instagram.com/outro/",
    )
    assert resultado is None


def _df_pautas_destaque():
    return pd.DataFrame(
        {
            "Topic": [0, 1, 2, 3],
            "Name": [
                "saude, hospital",
                "obras, ponte",
                "educacao, escola",
                "sem assunto definido",
            ],
            "score": [0.9, 0.5, 0.2, 0.8],
            "proporcao_sentimento_positivo": [0.9, 0.5, 0.2, 0.95],
        }
    )


def test_pauta_alto_positivo_pouco_publicada_escolhe_positiva_com_menos_reels_do_governador():
    # Governador tem 5 reels na pauta 1 e nenhum na 0: a pauta 0 (positiva,
    # volume 0) vence a 1. A degenerada (3, mais positiva) nunca e escolhida.
    resultado = produzir._pauta_alto_positivo_pouco_publicada(
        _df_pautas_destaque(), _discurso_governador([1, 1, 1, 1, 1])
    )
    assert resultado["topic"] == 0
    assert resultado["pauta"] == "saude, hospital"
    assert resultado["volume_reels"] == 0


def test_pauta_alto_positivo_pouco_publicada_degrada_sem_discurso_do_governador():
    resultado = produzir._pauta_alto_positivo_pouco_publicada(
        _df_pautas_destaque(), pd.DataFrame()
    )
    assert resultado == produzir.SEM_DADO_DISCURSO


def test_pauta_alto_positivo_pouco_publicada_none_sem_tabela_de_pautas():
    resultado = produzir._pauta_alto_positivo_pouco_publicada(
        pd.DataFrame(), _discurso_governador([0])
    )
    assert resultado is None


def test_pauta_alto_positivo_pouco_publicada_none_quando_positivo_todo_nulo():
    df = _df_pautas_destaque().iloc[:3].copy()
    df["proporcao_sentimento_positivo"] = float("nan")
    assert (
        produzir._pauta_alto_positivo_pouco_publicada(df, _discurso_governador([0]))
        is None
    )


def test_pauta_alto_positivo_pouco_publicada_none_so_com_degeneradas():
    df = _df_pautas_destaque().iloc[3:]
    assert (
        produzir._pauta_alto_positivo_pouco_publicada(df, _discurso_governador([3, 3]))
        is None
    )


def test_nenhuma_funcao_da_tela_usa_grupo_de_comentarios_na_fila():
    # Nada pendurado na fila de temas de comentario (issue #191).
    for nome in (
        "_topicos_do_governador",
        "_comentarios_do_tema",
        "_topico_prioritario_ajustado",
    ):
        assert not hasattr(produzir, nome), nome
    fonte = inspect.getsource(produzir.render)
    assert "load_topic_priority" not in fonte
    assert "load_topic_priority(" not in fonte
    assert "`topic_priority_score`" not in fonte


def test_evidencia_de_desempenho_nao_esta_mais_em_produzir():
    # ADR 0026 / issue #154: a evidência histórica de desempenho migrou
    # inteira para o Resumo -- prova estrutural de que não sobrou duplicata
    # morta aqui.
    assert not hasattr(produzir, "_conteudo_do_governador_por_tipo")
    assert not hasattr(produzir, "_serie_desempenho_por_publicacao")


def test_destaques_nao_alteram_logica_de_recomendacao_existente():
    # Prova estrutural: os destaques portados são puramente aditivos -- as
    # funções de recomendação não ganham nenhum parâmetro relacionado a eles.
    funcoes_recomendacao = (
        produzir._grupo_maior_engajamento,
        produzir._mapear_grupos_para_cartoes,
        produzir._recomendacao_principal,
        produzir._estatisticas_por_grupo,
    )
    parametros_novos = {"tipo", "metrica", "data_inicio", "data_fim"}
    for fn in funcoes_recomendacao:
        params = set(inspect.signature(fn).parameters)
        assert not params & parametros_novos, fn.__name__


# ---------------------------------------------------------------------------
# _melhor_post contra tabelas Delta reais (tmp_path) -- portado de
# tests/test_dashboard_screens_resumo.py junto com a função (ADR 0026 / issue
# #154), mesmo padrão de tests/test_dashboard_core_data.py.
# ---------------------------------------------------------------------------


def test_melhor_post_contra_tabelas_delta_reais(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    clusters_path = settings.GOLD_DIR / "governor_clusters_reels"
    write_deltalake(str(clusters_path), _df_clusters_conteudo(), mode="overwrite")

    reels_path = settings.SILVER_DIR / "reels_clean"
    write_deltalake(str(reels_path), _df_reels_conteudo(), mode="overwrite")

    df_clusters = data.load_clusters_content()
    df_reels = data.load_reels_content()

    resultado = produzir._melhor_post(df_clusters, df_reels, _GOV_URL)

    assert resultado is not None
    assert resultado["shortCode"] == "xyz"
    _clear_caches()


# ---------------------------------------------------------------------------
# Maiores grupos de comentarios (issue #192) -- por governador e sentimento.
# ---------------------------------------------------------------------------

_URL_A = "https://www.instagram.com/gov_a/"
_URL_B = "https://www.instagram.com/gov_b/"


def _linhas(url, topic, name, sentimento, n):
    return [
        {
            "inputUrl": url,
            "Topic": topic,
            "Name": name,
            "sentiment_label": sentimento,
            "text": f"c_{topic}_{sentimento}_{i}",
            "likesCount": i,
            "repliesCount": 0,
            "ownerUsername": "u",
            "timestamp": "2026-01-01",
        }
        for i in range(n)
    ]


def _df_grupos():
    linhas = (
        _linhas(_URL_A, 0, "0_obras_estrada", "positive", 4)
        + _linhas(_URL_A, 1, "Saude, saude, hospital", "positive", 3)
        + _linhas(_URL_A, 1, "Saude, saude, hospital", "negative", 2)
        + _linhas(_URL_A, 2, "2_escola_aula", "negative", 5)
        + _linhas(_URL_A, 2, "2_escola_aula", "neutral", 10)
        + _linhas(_URL_A, -1, "-1_ruido", "positive", 20)
        + _linhas(_URL_B, 0, "0_obras_estrada", "positive", 50)
    )
    return pd.DataFrame(linhas)


def test_grupos_positivos_contagem_pct_e_ruido_excluido():
    r = produzir._maiores_grupos_de_comentarios(_df_grupos(), _URL_A, "positive")
    assert list(r["Topic"]) == [0, 1]  # ruido (-1) fora, outro governador fora
    assert list(r["n"]) == [4, 3]
    # total do governador A = 4+3+2+5+10+20 = 44 (neutros e ruido contam)
    assert r["pct"].iloc[0] == 4 / 44


def test_grupos_negativos_so_dois_grupos_gera_duas_linhas():
    r = produzir._maiores_grupos_de_comentarios(_df_grupos(), _URL_A, "negative")
    assert list(r["Topic"]) == [2, 1]
    assert list(r["n"]) == [5, 2]


def test_grupos_top5_com_desempate_deterministico_por_topic():
    linhas = []
    for t in [7, 3, 5, 1, 9, 2, 4]:
        linhas += _linhas(_URL_A, t, f"{t}_x_y", "positive", 2)
    r = produzir._maiores_grupos_de_comentarios(
        pd.DataFrame(linhas), _URL_A, "positive"
    )
    assert list(r["Topic"]) == [1, 2, 3, 4, 5]


def test_grupos_governador_sem_negativos_fica_vazio():
    df = pd.DataFrame(_linhas(_URL_A, 0, "0_a_b", "positive", 3))
    assert produzir._maiores_grupos_de_comentarios(df, _URL_A, "negative").empty


def test_grupos_sem_comentarios_ou_sem_colunas_nao_quebra():
    vazio = pd.DataFrame()
    assert produzir._maiores_grupos_de_comentarios(vazio, _URL_A, "positive").empty
    sem_colunas = pd.DataFrame({"x": [1]})
    assert produzir._maiores_grupos_de_comentarios(
        sem_colunas, _URL_A, "positive"
    ).empty
    outro = _URL_B + "x"
    assert produzir._maiores_grupos_de_comentarios(
        _df_grupos(), outro, "positive"
    ).empty


def test_grupos_rotulo_bruto_refinado_e_degenerado():
    linhas = (
        _linhas(_URL_A, 0, "0_obras_estrada_ponte", "positive", 3)
        + _linhas(_URL_A, 1, "Saude publica, saude, hospital", "positive", 2)
        + _linhas(_URL_A, 2, None, "positive", 1)
    )
    r = produzir._maiores_grupos_de_comentarios(
        pd.DataFrame(linhas), _URL_A, "positive"
    )
    assert list(r["Grupo"]) == [
        "obras, estrada, ponte",
        "Saude publica",
        produzir.ROTULO_GRUPO_SEM_ROTULO,
    ]


def test_comentarios_do_grupo_filtra_governador_e_sentimento():
    r = produzir._comentarios_do_grupo(_df_grupos(), _URL_A, 0, "positive")
    assert len(r) == 4  # nao traz os 50 do governador B
    r2 = produzir._comentarios_do_grupo(_df_grupos(), _URL_A, 1, "negative")
    assert len(r2) == 2
    assert set(r2["sentiment_label"]) == {"negative"}


def test_comentarios_do_grupo_ordena_por_engajamento_e_limita():
    r = produzir._comentarios_do_grupo(_df_grupos(), _URL_A, 0, "positive", top_n=2)
    assert list(r["likesCount"]) == [3, 2]
    assert list(r.columns) == produzir._COLUNAS_COMENTARIOS_POPUP


def test_comentarios_do_grupo_vazio_com_colunas():
    for df in (pd.DataFrame(), _df_grupos()):
        r = produzir._comentarios_do_grupo(df, _URL_A, 99, "negative")
        assert r.empty
        assert list(r.columns) == produzir._COLUNAS_COMENTARIOS_POPUP
