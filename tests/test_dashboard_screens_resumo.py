"""Testes da Tela 1 ("Resumo da semana", ADR 0021 / issue #111).

Só a lógica pura de `dashboard/screens/resumo.py` é testada aqui (nível do
semáforo, seleção dos 4 destaques) -- nunca a renderização Streamlit em si,
mesmo padrão de `tests/test_dashboard_core_data.py`/`test_dashboard_loaders.py`
(issue #50). Um bloco final testa alguns desses caminhos contra tabelas Delta
reais escritas em `tmp_path`, mesmo padrão dos dois arquivos acima."""

import inspect

import pandas as pd
import pytest
import streamlit as st
from deltalake.writer import write_deltalake

from config import settings
from dashboard.core import data
from dashboard.core.deltas import LIMIAR_NEGATIVIDADE_ALERTA
from dashboard.screens import resumo


def _clear_caches():
    st.cache_resource.clear()
    st.cache_data.clear()


def _point_settings_at(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "GOLD_DIR", tmp_path / "gold")
    monkeypatch.setattr(settings, "SILVER_DIR", tmp_path / "silver")
    _clear_caches()


# ---------------------------------------------------------------------------
# _nivel_semaforo (frase de decisão)
# ---------------------------------------------------------------------------


def test_nivel_semaforo_verde_quando_os_dois_deltas_sobem():
    nivel = resumo._nivel_semaforo(
        delta_positivo=5.0, delta_engajamento=3.0, negatividade_atual=0.1
    )
    assert nivel == "good"


def test_nivel_semaforo_amarelo_quando_um_delta_cai():
    nivel = resumo._nivel_semaforo(
        delta_positivo=-2.0, delta_engajamento=3.0, negatividade_atual=0.1
    )
    assert nivel == "warn"


def test_nivel_semaforo_amarelo_quando_engajamento_cai():
    nivel = resumo._nivel_semaforo(
        delta_positivo=3.0, delta_engajamento=-1.0, negatividade_atual=0.1
    )
    assert nivel == "warn"


def test_nivel_semaforo_vermelho_quando_negatividade_cruza_limiar():
    nivel = resumo._nivel_semaforo(
        delta_positivo=5.0, delta_engajamento=5.0, negatividade_atual=0.35
    )
    assert nivel == "danger"


def test_nivel_semaforo_vermelho_tem_prioridade_sobre_deltas_positivos():
    # Mesmo com os dois deltas positivos, negatividade em alerta é o sinal
    # mais urgente (issue #111, user story 3: "vermelha quando a
    # negatividade cruzou o limite de alerta").
    nivel = resumo._nivel_semaforo(
        delta_positivo=10.0,
        delta_engajamento=10.0,
        negatividade_atual=LIMIAR_NEGATIVIDADE_ALERTA,
    )
    assert nivel == "danger"


def test_nivel_semaforo_neutro_com_historico_insuficiente_sem_quebrar():
    nivel = resumo._nivel_semaforo(
        delta_positivo=None, delta_engajamento=None, negatividade_atual=None
    )
    assert nivel == "info"


def test_frase_decisao_nao_quebra_para_qualquer_nivel():
    for nivel in ("good", "warn", "danger", "info"):
        texto = resumo._frase_decisao(nivel, delta_positivo=1.0, delta_engajamento=1.0)
        assert isinstance(texto, str) and texto


# ---------------------------------------------------------------------------
# Proporções de sentimento / formatação
# ---------------------------------------------------------------------------


def test_proporcao_label_calcula_fracao():
    df = pd.DataFrame({"sentiment_label": ["positive", "positive", "negative", "neutral"]})
    assert resumo._proporcao_label(df, "positive") == 0.5


def test_proporcao_label_retorna_none_para_dataframe_vazio():
    assert resumo._proporcao_label(pd.DataFrame(), "positive") is None


def test_fmt_pct_arredonda_e_nao_mostra_float_bruto():
    # Regressão direta da user story 11 -- nunca "71.428571%".
    assert resumo._fmt_pct(0.71428571) == "71.4%"


def test_fmt_pct_com_none_mostra_placeholder():
    assert resumo._fmt_pct(None) == "—"


def test_fmt_delta_pct_oculta_seta_quando_none():
    assert resumo._fmt_delta_pct(None) is None
    assert resumo._fmt_delta_pct(12.345) == "+12.3%"
    assert resumo._fmt_delta_pct(-3.0) == "-3.0%"


def test_fmt_int_br_usa_separador_de_milhar():
    assert resumo._fmt_int_br(12345) == "12.345"


# ---------------------------------------------------------------------------
# Delta genérico contra histórico (KPIs sem arrow quando insuficiente)
# ---------------------------------------------------------------------------


def _df_sentiment_history_dois_runs():
    return pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/gov_a/"] * 4,
            "sentiment_label": ["positive", "negative", "positive", "positive"],
            "_run_id": ["r1", "r1", "r2", "r2"],
        }
    )


def _df_sentiment_history_governador_por_janela_publicacao():
    # ADR 0027: `_delta_janela_publicacao_para_governador` usa data de
    # PUBLICAÇÃO, comparando os 7 dias-com-dado mais recentes (janela atual,
    # setembro, 1 comentário positivo por dia = 100%) contra os dias-com-dado
    # imediatamente anteriores (janela anterior, 4 dias em agosto, 2
    # positivos + 2 negativos = 50%) -- janela assimétrica aceita (ADR 0027),
    # não precisa ter os mesmos 7 dias dos dois lados.
    dias_anteriores = [f"2026-08-{d:02d}" for d in range(1, 5)]
    dias_atuais = [f"2026-09-{d:02d}" for d in range(1, 8)]
    sentimentos_anteriores = ["positive", "negative", "positive", "negative"]
    sentimentos_atuais = ["positive"] * 7

    linhas = [
        {"sentiment_label": sentimento, "timestamp": f"{dia}T10:00:00.000Z"}
        for dia, sentimento in zip(
            dias_anteriores + dias_atuais, sentimentos_anteriores + sentimentos_atuais, strict=True
        )
    ]
    return pd.DataFrame(linhas)


def test_delta_janela_publicacao_para_governador_compara_por_data_de_publicacao():
    resultado = resumo._delta_janela_publicacao_para_governador(
        _df_sentiment_history_governador_por_janela_publicacao()
    )
    assert resultado is not None
    valor_atual, delta_percentual, valor_anterior = resultado
    assert valor_atual == 1.0
    assert valor_anterior == 0.5
    assert delta_percentual > 0


def test_delta_janela_publicacao_para_governador_none_para_dataframe_vazio():
    assert resumo._delta_janela_publicacao_para_governador(pd.DataFrame()) is None


def test_delta_vs_media_historica_para_governador_usa_media_e_ignora_governador_ausente():
    df_history = pd.DataFrame(
        {
            "_chave": ["gov_a", "gov_a"],
            "_run_id": ["r1", "r2"],
            "pct_positivo": [0.5, 1.0],
        }
    )

    resultado = resumo._delta_vs_media_historica_para_governador(
        df_history, "pct_positivo", "gov_a"
    )
    assert resultado is not None
    valor_atual, _delta = resultado
    assert valor_atual == 1.0

    resultado_ausente = resumo._delta_vs_media_historica_para_governador(
        df_history, "pct_positivo", "gov_desconhecido"
    )
    assert resultado_ausente is None


def test_delta_vs_media_historica_para_governador_retorna_none_com_uma_execucao_so():
    df_uma_execucao = pd.DataFrame(
        {"_chave": ["gov_a"], "_run_id": ["r1"], "pct_positivo": [0.5]}
    )
    resultado = resumo._delta_vs_media_historica_para_governador(
        df_uma_execucao, "pct_positivo", "gov_a"
    )
    assert resultado is None


# ---------------------------------------------------------------------------
# ADR 0026 / issue #154: o filtro de calendário do gráfico de evidência NÃO
# pode vazar para a faixa de decisão nem para a tendência de engajamento/
# seguidores -- prova estrutural de que essas funções nunca ganham
# parâmetro de intervalo de datas.
# ---------------------------------------------------------------------------


def test_faixa_de_decisao_e_tendencia_de_engajamento_nao_aceitam_filtro_de_calendario():
    funcoes_fora_do_filtro = (
        resumo._nivel_semaforo,
        resumo._frase_decisao,
        resumo._delta_vs_media_historica_para_governador,
        resumo._delta_janela_publicacao_para_governador,
    )
    for fn in funcoes_fora_do_filtro:
        params = set(inspect.signature(fn).parameters)
        assert not params & {"data_inicio", "data_fim"}, fn.__name__


# ---------------------------------------------------------------------------
# Destaques removidos (ADR 0026 / issue #154) -- prova estrutural de que
# não sobrou duplicata morta em resumo.py depois da migração.
# ---------------------------------------------------------------------------


def test_destaques_antigos_nao_estao_mais_em_resumo():
    for nome in (
        "_melhor_post",
        "_maior_alta_negatividade",
        "_topico_alto_positivo_baixo_discurso",
        "_contagem_publicacoes_recentes",
        "_intervalo_disponivel",
        "SEM_DADO_DISCURSO",
    ):
        assert not hasattr(resumo, nome), nome


# ---------------------------------------------------------------------------
# Evidência histórica de desempenho (ADR 0026 / issue #154) -- migrada de
# `produzir.py` (ADR 0024) junto com os testes existentes (mesmo dado, mesma
# asserção), prova de que a realocação não mudou comportamento.
# ---------------------------------------------------------------------------

_GOV_URL_EVIDENCIA = "https://www.instagram.com/gov_a/"


def _df_reels_desempenho():
    return pd.DataFrame(
        {
            "inputUrl": [_GOV_URL_EVIDENCIA, _GOV_URL_EVIDENCIA],
            "likesCount": [100, 50],
            "commentsCount": [10, 5],
            "videoPlayCount": [1000, 2000],
            "data_hora": pd.to_datetime(["2026-08-01", "2026-08-02"]),
        }
    )


def _df_posts_desempenho():
    return pd.DataFrame(
        {
            "inputUrl": [_GOV_URL_EVIDENCIA],
            "likesCount": [30],
            "commentsCount": [3],
            "data_hora": pd.to_datetime(["2026-08-01"]),
        }
    )


def test_conteudo_do_governador_por_tipo_reels():
    resultado = resumo._conteudo_do_governador_por_tipo(
        _df_reels_desempenho(), _df_posts_desempenho(), _GOV_URL_EVIDENCIA, resumo.TIPO_REELS
    )
    assert len(resultado) == 2
    assert "videoPlayCount" in resultado.columns


def test_conteudo_do_governador_por_tipo_posts():
    resultado = resumo._conteudo_do_governador_por_tipo(
        _df_reels_desempenho(), _df_posts_desempenho(), _GOV_URL_EVIDENCIA, resumo.TIPO_POSTS
    )
    assert len(resultado) == 1


def test_conteudo_do_governador_por_tipo_ambos_combina_as_duas_fontes():
    resultado = resumo._conteudo_do_governador_por_tipo(
        _df_reels_desempenho(), _df_posts_desempenho(), _GOV_URL_EVIDENCIA, resumo.TIPO_AMBOS
    )
    assert len(resultado) == 3


def test_conteudo_do_governador_por_tipo_filtra_por_governador():
    resultado = resumo._conteudo_do_governador_por_tipo(
        _df_reels_desempenho(), _df_posts_desempenho(), "https://www.instagram.com/outro/",
        resumo.TIPO_AMBOS,
    )
    assert resultado.empty


def _conteudo_ambos_conhecido():
    return resumo._conteudo_do_governador_por_tipo(
        _df_reels_desempenho(), _df_posts_desempenho(), _GOV_URL_EVIDENCIA, resumo.TIPO_AMBOS
    )


def test_serie_desempenho_por_publicacao_soma_curtidas():
    df_conteudo = _conteudo_ambos_conhecido()
    resultado = resumo._serie_desempenho_por_publicacao(df_conteudo, resumo.METRICA_CURTIDAS)
    assert resultado["valor"].sum() == 180  # 100 + 50 (reels) + 30 (post)


def test_serie_desempenho_por_publicacao_conta_quantidade_de_publicacoes():
    df_conteudo = _conteudo_ambos_conhecido()
    resultado = resumo._serie_desempenho_por_publicacao(df_conteudo, resumo.METRICA_QUANTIDADE)
    assert resultado["valor"].sum() == 3


def test_serie_desempenho_por_publicacao_visualizacoes_vazio_para_posts_puros():
    # Posts de feed não têm videoPlayCount -- combinação sem sentido degrada
    # pra série vazia, nunca uma exceção.
    resultado = resumo._serie_desempenho_por_publicacao(
        _df_posts_desempenho(), resumo.METRICA_VISUALIZACOES
    )
    assert resultado.empty


def test_serie_desempenho_por_publicacao_quebra_em_segmentos_com_gap_maior_que_7_dias():
    df_reels = pd.DataFrame(
        {
            "inputUrl": [_GOV_URL_EVIDENCIA, _GOV_URL_EVIDENCIA],
            "likesCount": [100, 50],
            "data_hora": pd.to_datetime(["2026-08-01", "2026-08-20"]),
        }
    )
    df_conteudo = resumo._conteudo_do_governador_por_tipo(
        df_reels, pd.DataFrame(), _GOV_URL_EVIDENCIA, resumo.TIPO_REELS
    )
    serie = resumo._serie_desempenho_por_publicacao(df_conteudo, resumo.METRICA_CURTIDAS)

    segmentos = resumo.quebrar_em_segmentos(serie)

    assert len(segmentos) == 2
    assert len(segmentos[0]) == 1
    assert len(segmentos[1]) == 1


# ---------------------------------------------------------------------------
# _grafico_evidencia_desempenho (ADR 0029 / issue #173) -- função pura que
# constrói o `go.Figure` a partir da série já agregada; `render()` decide
# `st.plotly_chart` vs `st.caption` a partir do retorno (`None` = sem dado).
# ---------------------------------------------------------------------------


def test_grafico_evidencia_desempenho_um_trace_para_serie_continua():
    df_conteudo = _conteudo_ambos_conhecido()
    serie = resumo._serie_desempenho_por_publicacao(df_conteudo, resumo.METRICA_CURTIDAS)

    fig = resumo._grafico_evidencia_desempenho(serie, resumo.METRICA_CURTIDAS)

    assert fig is not None
    assert len(fig.data) == 1  # 01/08 e 02/08 -- gap de 1 dia, 1 segmento só
    assert fig.layout.yaxis.title.text == resumo.METRICA_CURTIDAS
    assert fig.layout.xaxis.title.text == "Data de publicação"


def test_grafico_evidencia_desempenho_um_trace_por_segmento_com_gap():
    df_reels = pd.DataFrame(
        {
            "inputUrl": [_GOV_URL_EVIDENCIA, _GOV_URL_EVIDENCIA],
            "likesCount": [100, 50],
            "data_hora": pd.to_datetime(["2026-08-01", "2026-08-20"]),
        }
    )
    df_conteudo = resumo._conteudo_do_governador_por_tipo(
        df_reels, pd.DataFrame(), _GOV_URL_EVIDENCIA, resumo.TIPO_REELS
    )
    serie = resumo._serie_desempenho_por_publicacao(df_conteudo, resumo.METRICA_CURTIDAS)

    fig = resumo._grafico_evidencia_desempenho(serie, resumo.METRICA_CURTIDAS)

    assert len(fig.data) == 2  # gap > 7 dias -- 2 segmentos, 1 trace cada


def test_grafico_evidencia_desempenho_none_para_serie_vazia():
    # Combinação sem dado real (Visualizações + Posts puros) -- `render()`
    # usa `None` pra decidir mostrar `st.caption` só deste gráfico, nunca
    # bloquear os outros 2 (ADR 0029, decisão 6).
    serie_vazia = resumo._serie_desempenho_por_publicacao(
        _df_posts_desempenho(), resumo.METRICA_VISUALIZACOES
    )
    assert resumo._grafico_evidencia_desempenho(serie_vazia, resumo.METRICA_VISUALIZACOES) is None


# ---------------------------------------------------------------------------
# render() -- 3 gráficos paralelos, sem seletor de Tipo nem filtro de
# período (ADR 0029 / issue #173). Verificação por inspeção de fonte, mesmo
# padrão de `test_legenda_de_metodologia_removida_do_resumo` -- o repo não
# usa `AppTest` do Streamlit.
# ---------------------------------------------------------------------------


def test_render_evidencia_nao_tem_mais_seletor_de_tipo_de_conteudo():
    codigo = inspect.getsource(resumo.render)
    assert "Tipo de conteúdo" not in codigo
    assert "resumo_tipo_conteudo" not in codigo


def test_render_evidencia_nao_tem_mais_filtro_de_periodo():
    codigo = inspect.getsource(resumo.render)
    assert "st.date_input" not in codigo
    assert "resumo_intervalo_desempenho" not in codigo
    assert not hasattr(resumo, "filter_by_date_range")
    assert not hasattr(resumo, "normalize_date_input_range")


def test_render_evidencia_renderiza_os_3_tipos_de_conteudo():
    codigo = inspect.getsource(resumo.render)
    assert "TIPO_AMBOS" in codigo
    assert "TIPO_POSTS" in codigo
    assert "TIPO_REELS" in codigo


# ---------------------------------------------------------------------------
# KPIs de crescimento (ADR 0026 / issue #154) -- CMGR/retenção, sem delta.
# ---------------------------------------------------------------------------


def test_campo_growth_le_coluna_da_linha():
    linha = pd.Series({"cmgr": 0.05, "cmgr_confiavel": True})
    assert resumo._campo_growth(linha, "cmgr") == 0.05
    assert resumo._campo_growth(linha, "cmgr_confiavel") is True


def test_campo_growth_none_quando_linha_e_none():
    assert resumo._campo_growth(None, "cmgr") is None


def test_campo_growth_none_quando_linha_nao_tem_a_coluna():
    linha = pd.Series({"cmgr": 0.05})
    assert resumo._campo_growth(linha, "retencao") is None


def test_kpi_crescimento_confiavel_mostra_valor_limpo_sem_selo():
    item = resumo._kpi_crescimento("CMGR", 0.05, confiavel=True, motivo=None)
    label, valor, delta, direcao, help_text = item
    assert label == "CMGR"
    assert valor == "5.0%"
    assert delta is None
    assert direcao is None
    assert help_text is None


def test_kpi_crescimento_pouco_confiavel_mostra_selo_e_motivo():
    item = resumo._kpi_crescimento(
        "Retenção", 0.10, confiavel=False, motivo="histórico curto"
    )
    label, valor, delta, _direcao, help_text = item
    assert label == "Retenção · ilustrativo"
    assert valor == "10.0%"
    assert delta is None
    assert help_text == "histórico curto"


def test_kpi_crescimento_sem_dado_degrada_para_placeholder_sem_selo():
    item = resumo._kpi_crescimento("CMGR", None, confiavel=None, motivo=None)
    label, valor, delta, _direcao, help_text = item
    assert label == "CMGR"
    assert valor == "—"
    assert delta is None
    assert help_text is None


# ---------------------------------------------------------------------------
# Governador (seleção / normalização de URL)
# ---------------------------------------------------------------------------


def test_governor_options_mapeia_nome_para_input_url():
    df_metadata = pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/gov_b/", "https://www.instagram.com/gov_a/"],
            "nome": ["Governador B", "Governador A"],
        }
    )
    opcoes = resumo._governor_options(df_metadata)
    assert opcoes == {
        "Governador A": "https://www.instagram.com/gov_a/",
        "Governador B": "https://www.instagram.com/gov_b/",
    }


def test_governor_options_vazio_quando_metadata_vazia():
    assert resumo._governor_options(pd.DataFrame()) == {}


def test_filtrar_por_governador_normaliza_barra_final_e_caixa():
    df = pd.DataFrame({"inputUrl": ["HTTPS://www.instagram.com/gov_a"]})
    filtrado = resumo._filtrar_por_governador(df, "https://www.instagram.com/gov_a/")
    assert len(filtrado) == 1


# ---------------------------------------------------------------------------
# Contra tabelas Delta reais (tmp_path) -- mesmo padrão de
# tests/test_dashboard_core_data.py / test_dashboard_loaders.py (issue #50)
# ---------------------------------------------------------------------------


def test_load_reels_content_retorna_vazio_quando_silver_nao_existe(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = data.load_reels_content()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_delta_positivo_contra_tabela_delta_real_de_sentiment_history(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    history_path = settings.GOLD_DIR / "governor_sentiment_history"
    df_history = _df_sentiment_history_governador_por_janela_publicacao().assign(
        inputUrl="https://www.instagram.com/gov_a/", fonte="comentario"
    )
    write_deltalake(str(history_path), df_history, mode="overwrite")

    df_sentiment_history = data.comments_only(data.load_sentiment_history())
    df_sentiment_history_governador = resumo._filtrar_por_governador(
        df_sentiment_history, "https://www.instagram.com/gov_a/"
    )
    resultado = resumo._delta_janela_publicacao_para_governador(df_sentiment_history_governador)

    assert resultado is not None
    valor_atual, _delta, _anterior = resultado
    assert valor_atual == 1.0
    _clear_caches()


# ---------------------------------------------------------------------------
# "Todos os Governadores" (ADR 0027 / issue #161) -- agregação SIMPLES, não
# ponderada por volume: cada governador pesa igual, nunca ponderado por
# quantos comentários/seguidores/publicações ele tem.
# ---------------------------------------------------------------------------


def test_legenda_de_metodologia_removida_do_resumo():
    """Issue #161: a legenda abaixo da faixa de decisão duplicava a mesma
    explicação já disponível via tooltip de cada KPI -- removida sem
    substituto."""
    codigo = inspect.getsource(resumo.render)
    assert "Engajamento, seguidores e NSM comparam" not in codigo


def test_filtrar_por_governador_ou_todos_devolve_tudo_para_sentinela():
    df = pd.DataFrame({"inputUrl": ["a", "b"], "valor": [1, 2]})
    out = resumo._filtrar_por_governador_ou_todos(df, resumo.TODOS_OS_GOVERNADORES)
    assert len(out) == 2


def test_filtrar_por_governador_ou_todos_filtra_normalmente_para_url_real():
    df = pd.DataFrame({"inputUrl": ["a", "b"], "valor": [1, 2]})
    out = resumo._filtrar_por_governador_ou_todos(df, "a")
    assert len(out) == 1
    assert out["valor"].iloc[0] == 1


def test_proporcao_media_por_governador_media_simples_nao_ponderada():
    # Governador "a": 1/2 positivo (0.5). Governador "b": 3/3 positivo
    # (1.0). Média simples = 0.75 -- NUNCA o pool ponderado por volume
    # (4/5 = 0.8, que daria mais peso a "b" por ter mais comentários).
    df = pd.DataFrame(
        {
            "sentiment_label": ["positive", "negative", "positive", "positive", "positive"],
            "_chave": ["a", "a", "b", "b", "b"],
        }
    )
    assert resumo._proporcao_media_por_governador(df, "positive") == pytest.approx(0.75)


def test_proporcao_media_por_governador_none_para_dataframe_vazio():
    assert resumo._proporcao_media_por_governador(pd.DataFrame(), "positive") is None


def test_media_simples_por_indice_ignora_chaves_com_none():
    resultado = {"a": (1.0, 10.0, 0.5), "b": (2.0, None, None), "c": (3.0, -5.0, 4.0)}
    assert resumo._media_simples_por_indice(resultado, 1) == pytest.approx((10.0 - 5.0) / 2)


def test_media_simples_por_indice_none_quando_todas_as_chaves_sao_none():
    resultado = {"a": (1.0, None, None)}
    assert resumo._media_simples_por_indice(resultado, 1) is None


def _df_sentiment_history_dois_governadores_para_agregado():
    # ADR 0027: governador "a" tem MUITO mais volume (10 comentários/dia)
    # que "b" (1/dia) -- de propósito, para provar que o agregado usa média
    # SIMPLES entre governadores, não o pool ponderado por volume (que
    # daria um resultado bem diferente, calculado no teste abaixo).
    dias_anteriores = [f"2026-08-{d:02d}" for d in range(1, 8)]
    dias_atuais = [f"2026-09-{d:02d}" for d in range(1, 8)]
    linhas = []
    # Governador "a": sempre positivo nos dois blocos -- estável (1.0 -> 1.0).
    for dia in dias_anteriores + dias_atuais:
        for i in range(10):
            linhas.append(
                {
                    "_chave": "gov_a",
                    "sentiment_label": "positive",
                    "timestamp": f"{dia}T10:{i:02d}:00.000Z",
                }
            )
    # Governador "b": negativo no bloco anterior, positivo no atual -- alta
    # real (0.0 -> 1.0).
    for dia in dias_anteriores:
        linhas.append(
            {"_chave": "gov_b", "sentiment_label": "negative", "timestamp": f"{dia}T11:00:00.000Z"}
        )
    for dia in dias_atuais:
        linhas.append(
            {"_chave": "gov_b", "sentiment_label": "positive", "timestamp": f"{dia}T11:00:00.000Z"}
        )
    return pd.DataFrame(linhas)


def test_delta_janela_publicacao_agregado_media_simples_nao_pondera_por_volume():
    df = _df_sentiment_history_dois_governadores_para_agregado()
    resultado = resumo._delta_janela_publicacao_agregado(df)

    assert resultado is not None
    valor_atual, delta_percentual, valor_anterior = resultado
    # Média simples: atual = (1.0["a"] + 1.0["b"]) / 2 = 1.0; anterior =
    # (1.0["a"] + 0.0["b"]) / 2 = 0.5 -- bem diferente do pool ponderado por
    # volume (que daria atual=1.0, anterior=70/77≈0.909, quase sem variação).
    assert valor_atual == pytest.approx(1.0)
    assert valor_anterior == pytest.approx(0.5)
    assert delta_percentual == pytest.approx(100.0)


def test_delta_janela_publicacao_agregado_none_para_dataframe_vazio():
    assert resumo._delta_janela_publicacao_agregado(pd.DataFrame()) is None


def test_agregar_metrica_todos_soma_ignora_nulos():
    df = pd.DataFrame({"followersCount": [100, 200, None]})
    assert resumo._agregar_metrica_todos(df, "followersCount", "sum") == 300


def test_agregar_metrica_todos_media_simples():
    df = pd.DataFrame({"% ENGAJAMENTO": [0.1, 0.3]})
    assert resumo._agregar_metrica_todos(df, "% ENGAJAMENTO", "mean") == pytest.approx(0.2)


def test_agregar_metrica_todos_none_para_dataframe_vazio():
    assert resumo._agregar_metrica_todos(pd.DataFrame(), "nsm", "mean") is None


def test_agregar_metrica_todos_none_sem_a_coluna():
    df = pd.DataFrame({"outra_coluna": [1, 2]})
    assert resumo._agregar_metrica_todos(df, "nsm", "mean") is None


def test_delta_vs_media_historica_agregado_soma_por_execucao_antes_de_comparar():
    # r1: soma dos 2 governadores = 300; r2: soma = 320; r3 (atual): soma =
    # 600 -- a comparação usa a SOMA de cada execução, nunca 1 governador
    # sozinho.
    df = pd.DataFrame(
        {
            "_run_id": ["r1", "r1", "r2", "r2", "r3", "r3"],
            "followersCount": [100, 200, 110, 210, 300, 300],
        }
    )
    resultado = resumo._delta_vs_media_historica_agregado(df, "followersCount", agg="sum")

    assert resultado is not None
    valor_atual, delta_percentual = resultado
    assert valor_atual == 600
    media_historica = (300 + 320) / 2
    assert delta_percentual == pytest.approx((600 - media_historica) / media_historica * 100)


def test_delta_vs_media_historica_agregado_none_com_uma_execucao_so():
    df = pd.DataFrame({"_run_id": ["r1", "r1"], "followersCount": [100, 200]})
    assert resumo._delta_vs_media_historica_agregado(df, "followersCount", agg="sum") is None


def test_delta_vs_media_historica_agregado_none_para_dataframe_vazio():
    assert resumo._delta_vs_media_historica_agregado(pd.DataFrame(), "nsm", agg="mean") is None


def test_proporcao_confiavel_conta_true_e_total():
    df = pd.DataFrame({"cmgr_confiavel": [True, False, True]})
    assert resumo._proporcao_confiavel(df, "cmgr_confiavel") == (2, 3)


def test_proporcao_confiavel_vazio_devolve_zero_zero():
    assert resumo._proporcao_confiavel(pd.DataFrame(), "cmgr_confiavel") == (0, 0)


def test_kpi_crescimento_agregado_nunca_ganha_sufixo_ilustrativo_e_sempre_declara_proporcao():
    label, _valor, delta, _direcao, help_text = resumo._kpi_crescimento_agregado(
        "CMGR", 0.05, 18, 26
    )
    assert label == "CMGR"  # nunca "CMGR · ilustrativo", mesmo com não confiáveis na média
    assert delta is None  # KPI de crescimento nunca tem seta (ADR 0026)
    assert help_text is not None
    assert "18 de 26" in help_text


def test_kpi_crescimento_agregado_sem_governadores_tooltip_vazio():
    label, _valor, _delta, _direcao, help_text = resumo._kpi_crescimento_agregado(
        "CMGR", None, 0, 0
    )
    assert label == "CMGR"
    assert help_text is None
