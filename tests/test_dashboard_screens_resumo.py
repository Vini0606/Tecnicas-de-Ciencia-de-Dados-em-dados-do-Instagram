"""Testes da Tela 1 ("Resumo da semana", ADR 0021 / issue #111).

Só a lógica pura de `dashboard/screens/resumo.py` é testada aqui (nível do
semáforo, seleção dos 4 destaques) -- nunca a renderização Streamlit em si,
mesmo padrão de `tests/test_dashboard_core_data.py`/`test_dashboard_loaders.py`
(issue #50). Um bloco final testa alguns desses caminhos contra tabelas Delta
reais escritas em `tmp_path`, mesmo padrão dos dois arquivos acima."""

import inspect

import pandas as pd
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
    # ADR 0025 / issue #153: `_delta_janela_publicacao_para_governador` usa
    # data de PUBLICAÇÃO, não `_run_id` -- âncora = 2026-09-08 (maior data).
    # Janela atual [09-02, 09-08] = 100% positivo; janela anterior
    # [08-26, 09-01] = 50% positivo.
    return pd.DataFrame(
        {
            "sentiment_label": ["positive", "negative", "positive", "positive"],
            "timestamp": [
                "2026-09-01T10:00:00.000Z",
                "2026-09-01T10:05:00.000Z",
                "2026-09-08T10:00:00.000Z",
                "2026-09-08T10:05:00.000Z",
            ],
        }
    )


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
# KPIs de crescimento (ADR 0026 / issue #154) -- CMGR/retenção, sem delta.
# ---------------------------------------------------------------------------


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
