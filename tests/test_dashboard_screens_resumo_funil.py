"""Testes da sub-aba "Funil de engajamento" do Resumo (ADR 0031 / issue #183; origem: issue #114).

Só a lógica pura de `dashboard/screens/funil.py` é testada aqui (agregação
por estágio, taxas de passagem, identificação do gargalo, escalonamento,
ação recomendada) -- nunca a renderização Streamlit em si, mesmo padrão de
`tests/test_dashboard_screens_{resumo,produzir,radar}.py`.

Cobre também o Engage·Criar (engajamento do UGC do piloto, ADR 0032), o
comparativo contra a mediana dos demais governadores e o HTML do funil em
escala logarítmica."""

from __future__ import annotations

import pandas as pd

from dashboard.screens import resumo_funil as funil
from dashboard.screens.resumo_comum import TODOS_OS_GOVERNADORES

_GOVERNOR_URL = "https://instagram.com/governador_a"


# ---------------------------------------------------------------------------
# _visualizacoes_reels_governador (Reach·Alcançar) -- null handling de
# `videoPlayCount` (issue #114, Testing Decisions).
# ---------------------------------------------------------------------------


def _df_clusters_reel(ids: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id_reel": ids,
            "ownerUsername": ["governador_a"] * len(ids),
            "content_type": ["reel"] * len(ids),
        }
    )


def _df_reels(ids: list[str], views: list[float | None]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": ids,
            "inputUrl": [_GOVERNOR_URL] * len(ids),
            "videoPlayCount": views,
        }
    )


def test_visualizacoes_reels_governador_soma_views_reais():
    df_clusters = _df_clusters_reel(["r1", "r2"])
    df_reels = _df_reels(["r1", "r2"], [100, 50])

    assert (
        funil._visualizacoes_reels_governador(df_clusters, df_reels, _GOVERNOR_URL)
        == 150.0
    )


def test_visualizacoes_reels_governador_exclui_nulos_da_soma_nunca_vira_nan():
    df_clusters = _df_clusters_reel(["r1", "r2", "r3"])
    df_reels = _df_reels(["r1", "r2", "r3"], [100, None, 50])

    total = funil._visualizacoes_reels_governador(df_clusters, df_reels, _GOVERNOR_URL)

    # 100 + 50 -- o reel com videoPlayCount nulo é EXCLUÍDO da soma, não
    # tratado como zero (que já daria o mesmo resultado neste caso), e o
    # total nunca é NaN.
    assert total == 150.0
    assert not pd.isna(total)


def test_visualizacoes_reels_governador_todos_nulos_retorna_zero_nunca_nan():
    df_clusters = _df_clusters_reel(["r1", "r2"])
    df_reels = _df_reels(["r1", "r2"], [None, None])

    total = funil._visualizacoes_reels_governador(df_clusters, df_reels, _GOVERNOR_URL)

    assert total == 0.0
    assert not pd.isna(total)


def test_visualizacoes_reels_governador_tabelas_vazias_retorna_zero():
    assert (
        funil._visualizacoes_reels_governador(
            pd.DataFrame(), pd.DataFrame(), _GOVERNOR_URL
        )
        == 0.0
    )


def test_visualizacoes_reels_governador_ignora_conteudo_que_nao_e_reel():
    df_clusters = pd.DataFrame(
        {
            "id_reel": ["p1"],
            "ownerUsername": ["governador_a"],
            "content_type": ["feed"],
        }
    )
    df_reels = _df_reels(["p1"], [999])

    # `p1` não tem cluster `content_type == 'reel'` -- não é encontrado no
    # merge, soma fica em 0.0 (não em 999, que seria de um post de feed).
    assert (
        funil._visualizacoes_reels_governador(df_clusters, df_reels, _GOVERNOR_URL)
        == 0.0
    )


# ---------------------------------------------------------------------------
# _consumir_likes_governador (Act·Consumir)
# ---------------------------------------------------------------------------


def test_consumir_likes_governador_le_likes_sum():
    df_engagement = pd.DataFrame({"inputUrl": [_GOVERNOR_URL], "likesSum": [500]})
    assert funil._consumir_likes_governador(df_engagement, _GOVERNOR_URL) == 500.0


def test_consumir_likes_governador_sem_match_retorna_zero():
    df_engagement = pd.DataFrame(
        {"inputUrl": ["https://instagram.com/outro"], "likesSum": [500]}
    )
    assert funil._consumir_likes_governador(df_engagement, _GOVERNOR_URL) == 0.0


# ---------------------------------------------------------------------------
# _contribuir_comentarios_positivos_governador (Convert·Contribuir)
# ---------------------------------------------------------------------------


def test_contribuir_comentarios_positivos_conta_so_positivos():
    df_sentiment = pd.DataFrame(
        {
            "inputUrl": [_GOVERNOR_URL] * 4,
            "sentiment_label": ["positive", "positive", "negative", "neutral"],
        }
    )
    assert (
        funil._contribuir_comentarios_positivos_governador(df_sentiment, _GOVERNOR_URL)
        == 2.0
    )


def test_contribuir_comentarios_positivos_vazio_retorna_zero():
    assert (
        funil._contribuir_comentarios_positivos_governador(
            pd.DataFrame(), _GOVERNOR_URL
        )
        == 0.0
    )


# ---------------------------------------------------------------------------
# _taxas_passagem / _identificar_gargalo (issue #114, Testing Decisions:
# gargalo óbvio, empate, dado insuficiente num estágio)
# ---------------------------------------------------------------------------


def test_taxas_passagem_calcula_as_duas_taxas():
    taxas = funil._taxas_passagem(reach=1000, act=500, convert=100)
    assert taxas[funil._ESTAGIO_ACT] == 0.5
    assert taxas[funil._ESTAGIO_CONVERT] == 0.2


def test_taxas_passagem_reach_zero_taxa_act_e_none():
    taxas = funil._taxas_passagem(reach=0, act=500, convert=100)
    assert taxas[funil._ESTAGIO_ACT] is None
    # Act/Reach é None, mas Convert/Act ainda é calculável.
    assert taxas[funil._ESTAGIO_CONVERT] == 0.2


def test_taxas_passagem_act_zero_taxa_convert_e_none():
    taxas = funil._taxas_passagem(reach=1000, act=0, convert=100)
    assert taxas[funil._ESTAGIO_CONVERT] is None


def test_identificar_gargalo_caso_obvio():
    # Act/Reach = 0.1 (gargalo óbvio), Convert/Act = 0.8.
    taxas = {funil._ESTAGIO_ACT: 0.1, funil._ESTAGIO_CONVERT: 0.8}
    assert funil._identificar_gargalo(taxas) == funil._ESTAGIO_ACT


def test_identificar_gargalo_caso_de_empate_prefere_estagio_mais_cedo():
    taxas = {funil._ESTAGIO_ACT: 0.3, funil._ESTAGIO_CONVERT: 0.3}
    # Empate -- desempatado pela ordem do funil (Act antes de Convert), ver
    # docstring do módulo, decisão 6.
    assert funil._identificar_gargalo(taxas) == funil._ESTAGIO_ACT


def test_identificar_gargalo_dado_insuficiente_em_um_estagio_e_excluido_nao_zerado():
    # Act/Reach é None (dado insuficiente) -- não deve ser tratado como 0.0
    # (que venceria artificialmente); só Convert tem dado real, então é o
    # gargalo por eliminação.
    taxas = {funil._ESTAGIO_ACT: None, funil._ESTAGIO_CONVERT: 0.4}
    assert funil._identificar_gargalo(taxas) == funil._ESTAGIO_CONVERT


def test_identificar_gargalo_nenhum_dado_real_retorna_none():
    taxas = {funil._ESTAGIO_ACT: None, funil._ESTAGIO_CONVERT: None}
    assert funil._identificar_gargalo(taxas) is None


# ---------------------------------------------------------------------------
# _convert_esta_caindo / _nivel_decisao -- escalonamento independente do
# gargalo (issue #114, Implementation Decisions)
# ---------------------------------------------------------------------------


def test_agregar_positivos_por_run_conta_por_execucao():
    df = pd.DataFrame(
        {
            "sentiment_label": ["positive", "negative", "positive", "positive"],
            "_run_id": ["r1", "r1", "r2", "r2"],
        }
    )
    agregado = funil._agregar_positivos_por_run(df)
    valores = dict(zip(agregado["_run_id"], agregado["qtd_positivos"], strict=True))
    assert valores == {"r1": 1, "r2": 2}


_CHAVE = funil._CHAVE_GOVERNADOR_UNICO


def test_convert_esta_caindo_true_quando_contagem_cai():
    df = pd.DataFrame(
        {"_chave": [_CHAVE, _CHAVE], "_run_id": ["r1", "r2"], "qtd_positivos": [10, 5]}
    )
    assert funil._convert_esta_caindo(df) is True


def test_convert_esta_caindo_false_quando_contagem_sobe():
    df = pd.DataFrame(
        {"_chave": [_CHAVE, _CHAVE], "_run_id": ["r1", "r2"], "qtd_positivos": [5, 10]}
    )
    assert funil._convert_esta_caindo(df) is False


def test_convert_esta_caindo_false_sem_historico_suficiente():
    df = pd.DataFrame({"_chave": [_CHAVE], "_run_id": ["r1"], "qtd_positivos": [5]})
    assert funil._convert_esta_caindo(df) is False


def test_nivel_decisao_escalona_para_warn_mesmo_sem_gargalo_absoluto():
    # Nenhum gargalo identificável (dado insuficiente), mas Convert caindo
    # -- ainda assim "warn" (issue #114: "subir a faixa de decisão para
    # amarelo mesmo que não seja o menor valor absoluto").
    assert funil._nivel_decisao(gargalo=None, convert_caindo=True) == "warn"


def test_nivel_decisao_warn_quando_ha_gargalo():
    assert (
        funil._nivel_decisao(gargalo=funil._ESTAGIO_ACT, convert_caindo=False) == "warn"
    )


def test_nivel_decisao_info_sem_gargalo_e_sem_queda():
    assert funil._nivel_decisao(gargalo=None, convert_caindo=False) == "info"


# ---------------------------------------------------------------------------
# _frase_decisao -- linguagem associativa, nunca causal (user story 8)
# ---------------------------------------------------------------------------


def test_frase_decisao_nunca_usa_linguagem_causal():
    frases = [
        funil._frase_decisao(gargalo=None, convert_caindo=False),
        funil._frase_decisao(gargalo=funil._ESTAGIO_ACT, convert_caindo=False),
        funil._frase_decisao(gargalo=funil._ESTAGIO_CONVERT, convert_caindo=False),
        funil._frase_decisao(gargalo=funil._ESTAGIO_CONVERT, convert_caindo=True),
    ]
    for frase in frases:
        assert "causa" not in frase.lower()
        assert " gera " not in frase.lower()


def test_frase_decisao_nomeia_o_estagio_gargalo():
    frase = funil._frase_decisao(gargalo=funil._ESTAGIO_CONVERT, convert_caindo=False)
    assert "contribuir" in frase.lower()


# ---------------------------------------------------------------------------
# _acao_recomendada -- negatividade em alta tem prioridade sobre o gargalo
# (issue #114, user story 6)
# ---------------------------------------------------------------------------


def test_acao_recomendada_negatividade_em_alta_aponta_para_radar():
    acao = funil._acao_recomendada(
        gargalo=funil._ESTAGIO_CONVERT, negatividade_em_alta=True
    )
    assert acao["alvo"] == funil._ACAO_RADAR
    assert acao["label_botao"] == f"Ver {funil._LABEL_TELA_RADAR}"


def test_acao_recomendada_gargalo_convert_aponta_para_produzir():
    acao = funil._acao_recomendada(
        gargalo=funil._ESTAGIO_CONVERT, negatividade_em_alta=False
    )
    assert acao["alvo"] == funil._ACAO_PRODUZIR


def test_acao_recomendada_gargalo_act_aponta_para_produzir():
    acao = funil._acao_recomendada(
        gargalo=funil._ESTAGIO_ACT, negatividade_em_alta=False
    )
    assert acao["alvo"] == funil._ACAO_PRODUZIR


def test_acao_recomendada_none_quando_nada_para_recomendar():
    assert funil._acao_recomendada(gargalo=None, negatividade_em_alta=False) is None


def test_acao_recomendada_texto_nunca_usa_linguagem_causal():
    acao = funil._acao_recomendada(
        gargalo=funil._ESTAGIO_ACT, negatividade_em_alta=False
    )
    assert "causa" not in acao["texto"].lower()
    assert " gera " not in acao["texto"].lower()


# ---------------------------------------------------------------------------
# Engage·Criar -- volume de UGC orgânico (ADR 0032, que revisa a proibição
# estrutural original da issue #114).
# ---------------------------------------------------------------------------


def _df_ugc() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "governor_username": ["Gov_A", "gov_a", "gov_b", "gov_b", "gov_c"],
            "likesCount": [10, 20, 100, None, 5],
            "commentsCount": [1, 2, 10, 4, 0],
            "is_organic": [True, True, True, False, True],
        }
    )


def test_username_de_url_normaliza_caixa_barra_e_query():
    assert funil._username_de_url("https://www.instagram.com/Gov_A/") == "gov_a"
    assert funil._username_de_url("https://www.instagram.com/gov_a/?hl=en") == "gov_a"
    assert funil._username_de_url(None) == ""
    assert funil._username_de_url(float("nan")) == ""


def test_engage_por_governador_conta_so_posts_organicos():
    out = funil._engage_por_governador(_df_ugc()).set_index("username")
    # caixa do username normalizada: Gov_A + gov_a = 2 posts
    assert out.loc["gov_a", "engage"] == 2
    # gov_b: a publi paga (is_organic=False) fica de fora -> 1 post
    assert out.loc["gov_b", "engage"] == 1
    assert out.loc["gov_c", "engage"] == 1


def test_engage_nao_depende_das_curtidas_de_um_post_viral():
    df = pd.DataFrame(
        {
            "governor_username": ["gov_x"] * 5,
            "likesCount": [29, 108, 53, 45, 13732],
            "commentsCount": [0, 6, 2, 6, 415],
            "is_organic": [True] * 5,
        }
    )
    assert funil._engage_para_selecao("https://instagram.com/gov_x/", df) == 5.0


def test_engage_por_governador_ignora_linha_sem_username():
    df = _df_ugc()
    df.loc[0, "governor_username"] = None
    out = funil._engage_por_governador(df).set_index("username")
    assert out.loc["gov_a", "engage"] == 1


def test_engage_por_governador_vazio_ou_sem_colunas_devolve_vazio():
    assert funil._engage_por_governador(pd.DataFrame()).empty
    assert funil._engage_por_governador(pd.DataFrame({"x": [1]})).empty
    so_pago = _df_ugc().assign(is_organic=False)
    assert funil._engage_por_governador(so_pago).empty


def test_engage_para_selecao_governador_unico_e_sem_ugc():
    assert funil._engage_para_selecao("https://instagram.com/gov_a/", _df_ugc()) == 2.0
    assert (
        funil._engage_para_selecao("https://instagram.com/nao_existe/", _df_ugc())
        == 0.0
    )
    assert (
        funil._engage_para_selecao("https://instagram.com/gov_a/", pd.DataFrame())
        == 0.0
    )


def test_engage_para_selecao_todos_e_media_por_governador_com_ugc():
    # gov_a 2, gov_b 1, gov_c 1 -> média simples entre governadores
    assert funil._engage_para_selecao(TODOS_OS_GOVERNADORES, _df_ugc()) == 4 / 3
    assert funil._engage_para_selecao(TODOS_OS_GOVERNADORES, pd.DataFrame()) == 0.0


def test_ugc_e_amostra_piloto_detecta_o_teto_e_some_com_coleta_maior():
    teto = funil._MAX_POSTS_UGC_PILOTO
    piloto = pd.DataFrame(
        {
            "governor_username": ["a"] * teto + ["b"] * 2,
            "is_organic": [True] * (teto + 2),
        }
    )
    assert funil._ugc_e_amostra_piloto(piloto) is True
    completa = pd.DataFrame(
        {
            "governor_username": ["a"] * (teto + 1) + ["b"] * 2,
            "is_organic": [True] * (teto + 3),
        }
    )
    assert funil._ugc_e_amostra_piloto(completa) is False
    assert funil._ugc_e_amostra_piloto(pd.DataFrame()) is False


def test_funil_nunca_liga_convert_ao_engage_em_taxa():
    taxas = funil._taxas_passagem(1000.0, 100.0, 10.0)
    assert set(taxas) == {"act", "convert"}


# ---------------------------------------------------------------------------
# Comparativo: valor ABSOLUTO de cada estágio vs. MEDIANA dos demais
# governadores (ADR 0032).
# ---------------------------------------------------------------------------


def _por_governador() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "url": [
                "https://instagram.com/gov_a/",
                "https://instagram.com/gov_b/",
                "https://instagram.com/gov_c/",
                "https://instagram.com/gov_d/",
            ],
            "reach": [100.0, 200.0, 400.0, 0.0],
            "act": [10.0, 20.0, 30.0, 40.0],
            "convert": [0.0, 5.0, 15.0, 25.0],
            "engage": [0.0, 0.0, 0.0, 0.0],
        }
    )


def test_diferencas_vs_mediana_usa_so_os_demais_com_valor_positivo():
    out = funil._diferencas_vs_mediana(
        {"reach": 150.0, "act": 60.0, "convert": 10.0},
        _por_governador(),
        "https://instagram.com/gov_a/",
    )
    # reach: demais com valor > 0 = b, c -> mediana 300 -> 150/300 - 1 = -0,5
    assert out["dif"]["reach"] == -0.5
    # act: demais = b, c, d -> mediana 30 -> 60/30 - 1 = +1
    assert out["dif"]["act"] == 1.0
    # convert: demais com valor > 0 = b, c, d -> mediana 15 -> 10/15 - 1
    assert abs(out["dif"]["convert"] - (10 / 15 - 1)) < 1e-9
    assert out["n"] == 3


def test_diferencas_vs_mediana_none_em_todos_sem_pares_ou_sem_valor():
    valores = {"reach": 150.0}
    assert (
        funil._diferencas_vs_mediana(valores, _por_governador(), TODOS_OS_GOVERNADORES)
        is None
    )
    assert (
        funil._diferencas_vs_mediana(
            valores, pd.DataFrame(), "https://instagram.com/gov_a/"
        )
        is None
    )
    # estágio sem dado (0) do selecionado não vira comparativo
    assert (
        funil._diferencas_vs_mediana(
            {"reach": 0.0}, _por_governador(), "https://instagram.com/gov_a/"
        )
        is None
    )


def test_estagios_com_engage_por_governador_junta_engage_pelo_username():
    base = funil._estagios_com_engage_por_governador(
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(
            {
                "inputUrl": [
                    "https://www.instagram.com/gov_a/",
                    "https://www.instagram.com/gov_z/",
                ],
                "likesSum": [10.0, 20.0],
            }
        ),
        pd.DataFrame(),
        _df_ugc(),
    ).set_index("url")
    assert base.loc["https://www.instagram.com/gov_a/", "engage"] == 2
    assert base.loc["https://www.instagram.com/gov_z/", "engage"] == 0


# ---------------------------------------------------------------------------
# Funil em escala logarítmica (ADR 0032)
# ---------------------------------------------------------------------------


def test_larguras_log_decresce_com_o_valor_e_respeita_o_minimo():
    larguras = funil._larguras_log((1_000_000_000.0, 1_000.0, 10.0))
    assert larguras[0] == 100.0
    assert larguras[0] > larguras[1] > larguras[2] >= funil._LARGURA_MIN_PCT
    # log10(10)/log10(1e9) = 11% < 14%: vira o mínimo
    assert larguras[2] == funil._LARGURA_MIN_PCT


def test_larguras_log_sem_dado_e_none_e_um_unico_estagio_ocupa_tudo():
    assert funil._larguras_log((1_000.0, 0.0, 0.0)) == [100.0, None, None]
    assert funil._larguras_log((0.0, 0.0, 0.0)) == [None, None, None]


def test_fmt_taxa_pct_usa_algarismos_significativos():
    assert funil._fmt_taxa_pct(0.2) == "20%"
    assert funil._fmt_taxa_pct(0.086) == "8,6%"
    assert funil._fmt_taxa_pct(0.00036) == "0,036%"


def test_html_funil_mostra_selos_de_taxa_gargalo_e_bloco_do_engage():
    estagios = (1_000_000.0, 100_000.0, 100.0)
    taxas = funil._taxas_passagem(*estagios)
    html = funil._html_funil(
        estagios, taxas, funil._identificar_gargalo(taxas), engage=3.0
    )
    assert "10% avançam" in html
    assert "0,10% avançam" in html
    assert "3,0% avançam" in html  # Convert -> Engage: 3 / 100
    assert html.count("gargalo") == 1  # Convert→Engage nunca é gargalo
    assert "Engage · Criar" in html
    assert "<b>3</b>" in html
    assert "posts de UGC orgânico" in html
    assert "piloto" not in html  # a tela não exibe aviso de piloto
    # sem governador selecionado: nenhuma seta de comparação e legenda explica
    assert "▲" not in html  # os selos de conversão usam só ▼
    assert "aparece ao selecionar um governador" in html


def test_html_funil_selo_engage_acima_de_100_pct_usa_multiplo():
    estagios = (1_000.0, 100.0, 10.0)
    taxas = funil._taxas_passagem(*estagios)
    html = funil._html_funil(estagios, taxas, None, engage=45.0)
    assert "▲ 4,5× a etapa anterior" in html


def test_html_funil_selo_engage_sem_dado_quando_falta_convert_ou_engage():
    estagios = (1_000.0, 100.0, 0.0)
    html = funil._html_funil(estagios, funil._taxas_passagem(*estagios), None, 5.0)
    assert 'f-pill-flow"><div class="f-pill">sem dado' in html
    estagios2 = (1_000.0, 100.0, 10.0)
    html2 = funil._html_funil(estagios2, funil._taxas_passagem(*estagios2), None, 0.0)
    assert 'f-pill-flow"><div class="f-pill">sem dado' in html2


def test_html_funil_com_comparativo_mostra_seta_e_percentual_absoluto():
    estagios = (1_000.0, 100.0, 10.0)
    taxas = funil._taxas_passagem(*estagios)
    comparativos = {"dif": {"reach": -0.67, "convert": 1.29, "engage": 0.5}, "n": 24}
    html = funil._html_funil(
        estagios, taxas, None, engage=40.0, comparativos=comparativos
    )
    assert "▼ 67%" in html
    assert "▲ 129%" in html
    assert "▲ 50%" in html  # no bloco do Engage
    assert "n = 24" in html


def test_html_funil_estagio_sem_dado_e_engage_sem_ugc_nao_quebram():
    estagios = (500_000.0, 40_000.0, 0.0)
    taxas = funil._taxas_passagem(*estagios)
    html = funil._html_funil(estagios, taxas, None)
    assert "sem dado" in html
    assert "nenhum post de UGC orgânico coletado" in html


def test_html_engage_todos_usa_texto_de_media_por_governador():
    html = funil._html_engage(4.3, None, is_todos=True)
    assert "média de posts de UGC orgânico por governador" in html
    assert "<b>4</b>" in html


def test_taxa_engage_e_none_sem_dado_e_pode_passar_de_100_pct():
    assert funil._taxa_engage(40.0, 5.0) == 0.125
    assert funil._taxa_engage(0.0, 5.0) is None
    assert funil._taxa_engage(40.0, 0.0) is None
    assert funil._taxa_engage(10.0, 45.0) == 4.5


def test_texto_como_ler_descreve_as_quatro_etapas_e_como_interpretar():
    for is_todos in (True, False):
        texto = funil._texto_como_ler(is_todos)
        for etapa in ("Reach", "Act", "Convert", "Engage"):
            assert etapa in texto
        assert "escala logarítmica" in texto
        assert "avançam" in texto
        assert "gargalo" in texto.lower()
    assert "média por governador" in funil._texto_como_ler(True)
    assert "diferença do valor dele" in funil._texto_como_ler(False)
    assert "mediana dos demais governadores" in funil._texto_como_ler(False)
    assert "mediana" not in funil._texto_como_ler(True)


def test_html_funil_nao_usa_a_palavra_alcance():
    estagios = (1_000.0, 100.0, 10.0)
    html = funil._html_funil(estagios, funil._taxas_passagem(*estagios), None)
    assert "Alcance" not in html


# ---------------------------------------------------------------------------
# Issue #183: seletor único do Resumo -- "Todos os Governadores" usa a MÉDIA
# por governador em cada estágio (ADR 0027), nunca a soma.
# ---------------------------------------------------------------------------

_URL_A = "https://instagram.com/gov_a"
_URL_B = "https://instagram.com/gov_b"


def _dados_dois_governadores():
    df_clusters = _df_clusters_reel(["a1", "b1"])
    df_reels = pd.DataFrame(
        {
            "id": ["a1", "b1"],
            "inputUrl": [_URL_A, _URL_B],
            "videoPlayCount": [1000, 3000],
        }
    )
    df_engagement = pd.DataFrame({"inputUrl": [_URL_A, _URL_B], "likesSum": [100, 300]})
    df_sent = pd.DataFrame(
        {
            "inputUrl": [_URL_A] * 2 + [_URL_B] * 4,
            "sentiment_label": ["positive", "negative"] + ["positive"] * 4,
        }
    )
    return df_clusters, df_reels, df_engagement, df_sent


def test_estagios_todos_e_media_por_governador_nao_soma():
    estagios = funil._estagios_para_selecao(
        TODOS_OS_GOVERNADORES, *_dados_dois_governadores()
    )
    assert estagios == (2000.0, 200.0, 2.5)  # soma seria (4000, 400, 5)


def test_estagios_governador_unico_nao_muda():
    estagios = funil._estagios_para_selecao(_URL_A, *_dados_dois_governadores())
    assert estagios == (1000.0, 100.0, 1.0)


def test_estagios_todos_ignora_governador_sem_dado_real_no_estagio():
    df_clusters, df_reels, df_engagement, df_sent = _dados_dois_governadores()
    df_reels = df_reels.assign(videoPlayCount=[1000, None])
    reach, _, _ = funil._estagios_para_selecao(
        TODOS_OS_GOVERNADORES, df_clusters, df_reels, df_engagement, df_sent
    )
    assert reach == 1000.0  # B sem dado nao puxa a media para 500


def test_estagios_todos_tabelas_vazias_devolve_zeros():
    vazio = pd.DataFrame()
    assert funil._estagios_para_selecao(
        TODOS_OS_GOVERNADORES, vazio, vazio, vazio, vazio
    ) == (
        0.0,
        0.0,
        0.0,
    )


def test_agregar_positivos_por_run_todos_usa_media_por_governador():
    df = pd.DataFrame(
        {
            "_chave": ["a", "a", "b"],
            "sentiment_label": ["positive", "positive", "positive"],
            "_run_id": ["r1", "r1", "r1"],
        }
    )
    agregado = funil._agregar_positivos_por_run(df, todos=True)
    assert list(agregado["qtd_positivos"]) == [
        1.5
    ]  # a=2, b=1 -> media 1.5 (soma seria 3)


def test_proporcao_negativo_todos_media_simples_nao_ponderada():
    df = pd.DataFrame(
        {
            "_chave": ["a"] * 4 + ["b"],
            "sentiment_label": ["negative"] * 4 + ["positive"],
        }
    )
    assert funil._proporcao_negativo_media_por_governador(df) == 0.5  # (1.0 + 0.0) / 2


def test_cores_dos_estagios_sao_tokens_claro_e_escuro_distintos_do_vermelho_iesb():
    for estagio, (claro, escuro) in funil.CORES_ESTAGIO.items():
        assert claro.startswith("#") and escuro.startswith("#"), estagio
        assert "d92936" not in (claro + escuro).lower(), estagio
