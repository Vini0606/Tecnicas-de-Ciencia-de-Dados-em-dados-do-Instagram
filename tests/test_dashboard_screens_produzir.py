"""Testes da Tela 2 ("O que produzir", ADR 0021 / issue #112).

Só a lógica pura de `dashboard/screens/produzir.py` é testada aqui (selo de
prioridade, mapeamento cluster -> cartão, recomendação principal) -- nunca a
renderização Streamlit em si, mesmo padrão de
`tests/test_dashboard_screens_resumo.py` (issue #111)."""

import inspect

import pandas as pd

from dashboard.screens import produzir

# ---------------------------------------------------------------------------
# _selo_prioridade / _cortes_tercis (selo de prioridade, nunca o score bruto)
# ---------------------------------------------------------------------------


def test_selo_prioridade_alta_quando_score_igual_ao_corte_alta():
    assert produzir._selo_prioridade(0.5, corte_alta=0.5, corte_media=0.2) == produzir.SELO_ALTA


def test_selo_prioridade_alta_acima_do_corte():
    assert produzir._selo_prioridade(0.9, corte_alta=0.5, corte_media=0.2) == produzir.SELO_ALTA


def test_selo_prioridade_media_entre_os_dois_cortes():
    assert produzir._selo_prioridade(0.3, corte_alta=0.5, corte_media=0.2) == produzir.SELO_MEDIA


def test_selo_prioridade_media_no_valor_de_fronteira():
    # score == corte_media entra na banda "média" (inclusivo do lado alto).
    assert produzir._selo_prioridade(0.2, corte_alta=0.5, corte_media=0.2) == produzir.SELO_MEDIA


def test_selo_prioridade_cuidado_abaixo_do_corte_media():
    assert (
        produzir._selo_prioridade(0.1, corte_alta=0.5, corte_media=0.2) == produzir.SELO_CUIDADO
    )


def test_selo_prioridade_cuidado_para_score_nulo():
    assert produzir._selo_prioridade(None, corte_alta=0.5, corte_media=0.2) == produzir.SELO_CUIDADO
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
# _fila_prioridade -- filtrada ao governador (topic_priority_score não tem
# inputUrl, ver docstring do módulo) + estado vazio amigável
# ---------------------------------------------------------------------------


def _df_topic_priority_global():
    # Ranking GLOBAL (sem inputUrl) -- 4 tópicos, scores bem espalhados para
    # cair em bandas diferentes.
    return pd.DataFrame(
        {
            "Topic": [0, 1, 2, 3],
            "Name": ["0_saude", "1_seguranca", "2_educacao", "3_infra"],
            "score": [0.9, 0.6, 0.3, 0.05],
            "proporcao_sentimento_positivo": [0.8, 0.5, 0.4, 0.2],
        }
    )


def test_fila_prioridade_restringe_ao_governador_e_ordena_por_score():
    # Governador só comentou nos tópicos 1 e 3 -- 0 e 2 não devem aparecer,
    # mesmo tendo score mais alto (são de OUTRO governador).
    fila = produzir._fila_prioridade(_df_topic_priority_global(), topicos_governador={1, 3})

    assert list(fila["Topic"]) == [1, 3]
    assert list(fila["Name"]) == ["1_seguranca", "3_infra"]
    # Nunca a coluna de score bruto exposta na fila renderizável -- mas
    # internamente o score ainda está presente para uso de
    # `_topico_prioritario_ajustado`.
    assert "score" in fila.columns
    assert "Prioridade" in fila.columns


def test_fila_prioridade_vazia_quando_topic_priority_vazio():
    fila = produzir._fila_prioridade(pd.DataFrame(), topicos_governador={1})
    assert fila.empty
    assert list(fila.columns) == produzir._COLUNAS_FILA


def test_fila_prioridade_vazia_quando_governador_sem_topicos_proprios():
    fila = produzir._fila_prioridade(_df_topic_priority_global(), topicos_governador=set())
    assert fila.empty


def test_topicos_do_governador_extrai_topics_distintos():
    df = pd.DataFrame({"Topic": [0, 0, 2, None]})
    assert produzir._topicos_do_governador(df) == {0, 2}


def test_topicos_do_governador_vazio_sem_quebrar():
    assert produzir._topicos_do_governador(pd.DataFrame()) == set()


# ---------------------------------------------------------------------------
# Regressão de escopo -- a fila de OUTRO governador não pode vazar
# (mesma classe de bug corrigida na Tela 1, issue #111 -- ver CLAUDE.md/
# handoff do issue #112)
# ---------------------------------------------------------------------------


def test_fila_prioridade_nao_mistura_topico_de_outro_governador_com_sinal_maior():
    df_topic_priority = pd.DataFrame(
        {
            "Topic": [0, 1],
            "Name": ["0_do_governador_selecionado", "1_de_outro_governador_com_score_maior"],
            "score": [0.2, 0.99],
            "proporcao_sentimento_positivo": [0.5, 0.9],
        }
    )
    # O governador selecionado só tem comentário no tópico 0 -- o tópico 1
    # (score muito maior) pertence a outro perfil e não pode aparecer.
    fila = produzir._fila_prioridade(df_topic_priority, topicos_governador={0})

    assert list(fila["Topic"]) == [0]
    assert list(fila["Name"]) == ["0_do_governador_selecionado"]


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
# _topico_prioritario_ajustado / _recomendacao_principal
# ---------------------------------------------------------------------------


def _fila_dois_temas():
    return pd.DataFrame(
        {
            "Topic": [0, 1],
            "Name": ["0_muito_coberto", "1_pouco_coberto"],
            "score": [0.9, 0.5],
            "proporcao_sentimento_positivo": [0.8, 0.6],
            "Prioridade": [produzir.SELO_ALTA, produzir.SELO_MEDIA],
        }
    )


def test_topico_prioritario_ajustado_pula_tema_muito_coberto_pelo_discurso():
    df_discurso = pd.DataFrame({"Topic": [0, 0, 0, 0, 0, 1]})
    resultado = produzir._topico_prioritario_ajustado(_fila_dois_temas(), df_discurso)
    assert resultado["Name"] == "1_pouco_coberto"


def test_topico_prioritario_ajustado_usa_topo_sem_dado_de_discurso():
    resultado = produzir._topico_prioritario_ajustado(_fila_dois_temas(), pd.DataFrame())
    assert resultado["Name"] == "0_muito_coberto"


def test_topico_prioritario_ajustado_none_com_fila_vazia():
    assert produzir._topico_prioritario_ajustado(pd.DataFrame(), pd.DataFrame()) is None


def test_recomendacao_principal_combina_tema_e_formato_calculados():
    cartoes = {
        produzir.GRUPO_CURTO: {"n": 5, "engajamento_medio": 100.0},
        produzir.GRUPO_VIRAL: {"n": 2, "engajamento_medio": 900.0},
    }
    recomendacao = produzir._recomendacao_principal(_fila_dois_temas(), pd.DataFrame(), cartoes)
    assert recomendacao == {"topic_name": "0_muito_coberto", "grupo": produzir.GRUPO_VIRAL}


def test_recomendacao_principal_none_sem_cartoes():
    recomendacao = produzir._recomendacao_principal(_fila_dois_temas(), pd.DataFrame(), {})
    assert recomendacao is None


def test_recomendacao_principal_none_sem_fila():
    cartoes = {produzir.GRUPO_CURTO: {"n": 5, "engajamento_medio": 100.0}}
    recomendacao = produzir._recomendacao_principal(pd.DataFrame(), pd.DataFrame(), cartoes)
    assert recomendacao is None


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
# Evidência histórica de desempenho (ADR 0024) -- seção aditiva, não deve
# mudar nenhum resultado das funções de recomendação testadas acima.
# ---------------------------------------------------------------------------

_GOV_URL = "https://www.instagram.com/gov_a/"


def _df_reels_desempenho():
    return pd.DataFrame(
        {
            "inputUrl": [_GOV_URL, _GOV_URL],
            "likesCount": [100, 50],
            "commentsCount": [10, 5],
            "videoPlayCount": [1000, 2000],
            "data_hora": pd.to_datetime(["2026-08-01", "2026-08-02"]),
        }
    )


def _df_posts_desempenho():
    return pd.DataFrame(
        {
            "inputUrl": [_GOV_URL],
            "likesCount": [30],
            "commentsCount": [3],
            "data_hora": pd.to_datetime(["2026-08-01"]),
        }
    )


def test_conteudo_do_governador_por_tipo_reels():
    resultado = produzir._conteudo_do_governador_por_tipo(
        _df_reels_desempenho(), _df_posts_desempenho(), _GOV_URL, produzir.TIPO_REELS
    )
    assert len(resultado) == 2
    assert "videoPlayCount" in resultado.columns


def test_conteudo_do_governador_por_tipo_posts():
    resultado = produzir._conteudo_do_governador_por_tipo(
        _df_reels_desempenho(), _df_posts_desempenho(), _GOV_URL, produzir.TIPO_POSTS
    )
    assert len(resultado) == 1


def test_conteudo_do_governador_por_tipo_ambos_combina_as_duas_fontes():
    resultado = produzir._conteudo_do_governador_por_tipo(
        _df_reels_desempenho(), _df_posts_desempenho(), _GOV_URL, produzir.TIPO_AMBOS
    )
    assert len(resultado) == 3


def test_conteudo_do_governador_por_tipo_filtra_por_governador():
    resultado = produzir._conteudo_do_governador_por_tipo(
        _df_reels_desempenho(), _df_posts_desempenho(), "https://www.instagram.com/outro/",
        produzir.TIPO_AMBOS,
    )
    assert resultado.empty


def test_serie_desempenho_por_publicacao_soma_curtidas():
    df_conteudo = _conteudo_ambos_conhecido()
    resultado = produzir._serie_desempenho_por_publicacao(df_conteudo, produzir.METRICA_CURTIDAS)
    assert resultado["valor"].sum() == 180  # 100 + 50 (reels) + 30 (post)


def test_serie_desempenho_por_publicacao_conta_quantidade_de_publicacoes():
    df_conteudo = _conteudo_ambos_conhecido()
    resultado = produzir._serie_desempenho_por_publicacao(
        df_conteudo, produzir.METRICA_QUANTIDADE
    )
    assert resultado["valor"].sum() == 3


def test_serie_desempenho_por_publicacao_visualizacoes_vazio_para_posts_puros():
    # ADR 0024: posts de feed não têm videoPlayCount -- combinação sem
    # sentido degrada pra série vazia, nunca uma exceção.
    resultado = produzir._serie_desempenho_por_publicacao(
        _df_posts_desempenho(), produzir.METRICA_VISUALIZACOES
    )
    assert resultado.empty


def _conteudo_ambos_conhecido():
    return produzir._conteudo_do_governador_por_tipo(
        _df_reels_desempenho(), _df_posts_desempenho(), _GOV_URL, produzir.TIPO_AMBOS
    )


def test_evidencia_de_desempenho_nao_altera_logica_de_recomendacao_existente():
    # Prova estrutural (ADR 0024): a nova seção é puramente aditiva -- as
    # funções de recomendação não ganham nenhum parâmetro relacionado a tipo
    # de conteúdo/métrica/data de publicação.
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
