"""Testes da Tela 1 ("Resumo da semana", ADR 0021 / issue #111).

Só a lógica pura de `dashboard/screens/resumo.py` é testada aqui (nível do
semáforo, seleção dos 4 destaques) -- nunca a renderização Streamlit em si,
mesmo padrão de `tests/test_dashboard_core_data.py`/`test_dashboard_loaders.py`
(issue #50). Um bloco final testa alguns desses caminhos contra tabelas Delta
reais escritas em `tmp_path`, mesmo padrão dos dois arquivos acima."""

import datetime
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


def test_agregar_pct_positivo_por_run_pre_agrega_por_chave_e_execucao():
    agregado = resumo._agregar_pct_positivo_por_run(_df_sentiment_history_dois_runs())

    assert set(agregado["_run_id"]) == {"r1", "r2"}
    linha_r2 = agregado[agregado["_run_id"] == "r2"].iloc[0]
    assert linha_r2["pct_positivo"] == 1.0


def test_delta_para_governador_usa_week_over_week_e_ignora_governador_ausente():
    agregado = resumo._agregar_pct_positivo_por_run(_df_sentiment_history_dois_runs())

    resultado = resumo._delta_para_governador(
        agregado, "pct_positivo", "https://www.instagram.com/gov_a/"
    )
    assert resultado is not None
    valor_atual, _delta = resultado
    assert valor_atual == 1.0

    resultado_ausente = resumo._delta_para_governador(
        agregado, "pct_positivo", "https://www.instagram.com/gov_desconhecido/"
    )
    assert resultado_ausente is None


def test_delta_para_governador_retorna_none_com_uma_execucao_so():
    df_uma_execucao = pd.DataFrame(
        {"_chave": ["gov_a"], "_run_id": ["r1"], "pct_positivo": [0.5]}
    )
    resultado = resumo._delta_para_governador(df_uma_execucao, "pct_positivo", "gov_a")
    assert resultado is None


# ---------------------------------------------------------------------------
# Destaque 1 -- melhor post/reel
# ---------------------------------------------------------------------------


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
            "inputUrl": ["https://www.instagram.com/gov_a/"] * 3,
            "shortCode": ["abc", "xyz", "feed1"],
            "Total de Engajamento": [100, 500, 900],
        }
    )


def test_melhor_post_escolhe_maior_engajamento_entre_reels_do_governador():
    resultado = resumo._melhor_post(
        _df_clusters_conteudo(), _df_reels_conteudo(), "https://www.instagram.com/gov_a/"
    )

    assert resultado is not None
    # "p1" tem o maior engajamento (900), mas é content_type == "feed" --
    # não deve ser escolhido; entre os reels, "r2" (500) vence "r1" (100).
    assert resultado["shortCode"] == "xyz"
    assert resultado["total_engajamento"] == 500


def test_melhor_post_retorna_none_quando_tabelas_vazias():
    assert resumo._melhor_post(pd.DataFrame(), pd.DataFrame(), "url") is None
    assert resumo._melhor_post(_df_clusters_conteudo(), pd.DataFrame(), "url") is None


def test_melhor_post_retorna_none_sem_reel_do_governador():
    resultado = resumo._melhor_post(
        _df_clusters_conteudo(), _df_reels_conteudo(), "https://www.instagram.com/outro_gov/"
    )
    assert resultado is None


# ---------------------------------------------------------------------------
# Destaque 2 -- tema com maior % negativo no período de publicação (ADR 0023
# -- SUBSTITUI o critério anterior de "maior aumento entre as 2 execuções
# mais recentes": não há mais noção de "atual vs. anterior" quando o eixo
# passa a ser a data real de publicação do comentário, ver docstring de
# `_maior_alta_negatividade`).
# ---------------------------------------------------------------------------


def _df_sentiment_history_topicos_por_publicacao():
    return pd.DataFrame(
        {
            "id_comment": [f"c{i}" for i in range(8)],
            "Topic": [0, 0, 0, 0, 1, 1, 1, 1],
            "Name": ["0_saude"] * 4 + ["1_seguranca"] * 4,
            "sentiment_label": [
                # Tópico 0: 3/4 negativo no período = 75%
                "negative",
                "negative",
                "negative",
                "positive",
                # Tópico 1: 1/4 negativo no período = 25%
                "negative",
                "positive",
                "positive",
                "positive",
            ],
            "timestamp": [
                "2026-08-01T10:00:00.000Z",
                "2026-08-02T10:00:00.000Z",
                "2026-08-03T10:00:00.000Z",
                "2026-08-04T10:00:00.000Z",
                "2026-08-01T11:00:00.000Z",
                "2026-08-02T11:00:00.000Z",
                "2026-08-03T11:00:00.000Z",
                "2026-08-04T11:00:00.000Z",
            ],
            "_run_id": ["r1"] * 8,
        }
    )


def test_maior_alta_negatividade_escolhe_topico_com_maior_pct_negativo_no_periodo():
    resultado = resumo._maior_alta_negatividade(_df_sentiment_history_topicos_por_publicacao())

    assert resultado is not None
    assert resultado["topic"] == 0
    assert resultado["name"] == "0_saude"
    assert resultado["pct_negativo"] == 75.0


def test_maior_alta_negatividade_respeita_filtro_de_intervalo():
    df = _df_sentiment_history_topicos_por_publicacao()

    # Restringindo ao dia 1/ago só: tópico 0 tem 1 comentário negativo (100%),
    # tópico 1 tem 1 comentário negativo (100%) -- empate, mas cortar o
    # período muda o resultado em relação ao período completo (onde tópico 0
    # vence com folga, 75% vs. 25%) -- prova que o filtro de fato altera
    # o dado agregado, não só decora a chamada.
    resultado_periodo_completo = resumo._maior_alta_negatividade(df)
    resultado_um_dia = resumo._maior_alta_negatividade(
        df, data_inicio=datetime.date(2026, 8, 4), data_fim=datetime.date(2026, 8, 4)
    )

    assert resultado_periodo_completo["topic"] == 0
    # Só o dia 4/ago: tópico 0 tem 1 comentário positivo (0% negativo, fora
    # dos candidatos); tópico 1 tem 1 comentário positivo (0% negativo,
    # também fora) -- nenhum tópico com negatividade > 0 nesse recorte.
    assert resultado_um_dia is None


def test_maior_alta_negatividade_deduplica_comentario_recoletado_entre_execucoes():
    df = pd.DataFrame(
        {
            # Mesmo comentário (c1) recoletado em r1 e r2 -- sem dedup,
            # contaria 2x como negativo no mesmo dia, inflando o tópico 0.
            "id_comment": ["c1", "c1", "c2"],
            "Topic": [0, 0, 1],
            "Name": ["0_saude", "0_saude", "1_seguranca"],
            "sentiment_label": ["negative", "negative", "negative"],
            "timestamp": ["2026-08-01T10:00:00.000Z"] * 2 + ["2026-08-01T11:00:00.000Z"],
            "_run_id": ["r1", "r2", "r1"],
        }
    )
    resultado = resumo._maior_alta_negatividade(df)

    # Com dedup, tópico 0 e tópico 1 têm 1 comentário negativo cada (100%) --
    # empate resolvido por ordem estável, mas o ponto é que tópico 0 NÃO
    # domina com "2 comentários negativos" que na verdade são o mesmo.
    assert resultado is not None
    assert resultado["pct_negativo"] == 100.0


def test_maior_alta_negatividade_retorna_none_sem_topico_atribuido():
    df = _df_sentiment_history_topicos_por_publicacao()
    df["Topic"] = None
    assert resumo._maior_alta_negatividade(df) is None


def test_maior_alta_negatividade_retorna_none_quando_nenhum_topico_tem_negatividade():
    df = _df_sentiment_history_topicos_por_publicacao()
    df["sentiment_label"] = "positive"
    assert resumo._maior_alta_negatividade(df) is None


def test_maior_alta_negatividade_retorna_none_para_dataframe_vazio():
    assert resumo._maior_alta_negatividade(pd.DataFrame()) is None


def _df_sentiment_history_dois_governadores():
    """Dois governadores no mesmo histórico -- gov_b tem % negativo no
    período MUITO maior que gov_a (100% vs. 75%), pra provar que o destaque 2
    precisa ser calculado sobre o histórico JÁ FILTRADO ao governador
    selecionado (`render()` faz isso via `_filtrar_por_governador` antes de
    chamar `_maior_alta_negatividade` -- ver bug corrigido: sem esse filtro,
    o destaque misturava os 27 perfis e sempre "vencia" o governador com a
    pior semana, não o perfil que a analista escolheu)."""
    gov_a = "https://www.instagram.com/gov_a/"
    gov_b = "https://www.instagram.com/gov_b/"
    df = _df_sentiment_history_topicos_por_publicacao().assign(inputUrl=gov_a)
    df_b = pd.DataFrame(
        {
            "id_comment": ["b1", "b2"],
            "inputUrl": [gov_b] * 2,
            "Topic": [5, 5],
            "Name": ["5_seguranca"] * 2,
            "sentiment_label": ["negative", "negative"],
            "timestamp": ["2026-08-01T12:00:00.000Z", "2026-08-02T12:00:00.000Z"],
            "_run_id": ["r1"] * 2,
        }
    )
    return pd.concat([df, df_b], ignore_index=True)


def test_maior_alta_negatividade_ignora_outros_governadores_quando_historico_e_filtrado():
    df_todos = _df_sentiment_history_dois_governadores()
    gov_a = "https://www.instagram.com/gov_a/"

    # Sanity check: sem filtrar por governador, o tópico vencedor é o de
    # gov_b (100% negativo) -- é exatamente esse resultado errado que o bug
    # produzia quando `render()` passava o histórico inteiro (todos os 27
    # perfis) direto para `_maior_alta_negatividade`.
    resultado_sem_filtro = resumo._maior_alta_negatividade(df_todos)
    assert resultado_sem_filtro is not None
    assert resultado_sem_filtro["topic"] == 5

    # Com o histórico filtrado ao governador selecionado (gov_a) -- o que
    # `render()` agora faz antes de chamar `_maior_alta_negatividade` --, o
    # destaque precisa ser o próprio tópico de gov_a, mesmo sendo uma
    # negatividade menor que a de gov_b.
    df_governador = resumo._filtrar_por_governador(df_todos, gov_a)
    resultado_filtrado = resumo._maior_alta_negatividade(df_governador)

    assert resultado_filtrado is not None
    assert resultado_filtrado["topic"] == 0
    assert resultado_filtrado["name"] == "0_saude"
    assert resultado_filtrado["pct_negativo"] == 75.0


# ---------------------------------------------------------------------------
# _intervalo_disponivel -- limites do filtro de calendário do destaque 2
# ---------------------------------------------------------------------------


def test_intervalo_disponivel_retorna_data_minima_e_maxima():
    df = _df_sentiment_history_topicos_por_publicacao()
    intervalo = resumo._intervalo_disponivel(df)
    assert intervalo == (datetime.date(2026, 8, 1), datetime.date(2026, 8, 4))


def test_intervalo_disponivel_none_sem_coluna_timestamp():
    assert resumo._intervalo_disponivel(pd.DataFrame({"Topic": [0]})) is None


def test_intervalo_disponivel_none_com_dataframe_vazio():
    assert resumo._intervalo_disponivel(pd.DataFrame()) is None


# ---------------------------------------------------------------------------
# Destaque 4 -- contagem de publicações recentes (ADR 0024, substitui o
# gráfico de tendência "por coleta" que vivia no rodapé)
# ---------------------------------------------------------------------------


def _df_reels_com_data(datas: list, governor_url: str = "https://www.instagram.com/gov_a/"):
    return pd.DataFrame(
        {
            "inputUrl": [governor_url] * len(datas),
            "data_hora": pd.to_datetime(datas),
        }
    )


def test_contagem_publicacoes_recentes_conta_reels_e_posts_combinados():
    df_reels = _df_reels_com_data(["2026-08-01", "2026-08-05"])
    df_posts = _df_reels_com_data(["2026-08-04"])

    resultado = resumo._contagem_publicacoes_recentes(
        df_reels, df_posts, "https://www.instagram.com/gov_a/"
    )

    assert resultado is not None
    quantidade, janela_dias = resultado
    # Janela termina na data mais recente disponível (5/ago, não "hoje") e
    # olha pra trás `_JANELA_DESTAQUE_PUBLICACOES_DIAS` dias -- as 3
    # publicações (1/ago, 4/ago, 5/ago) caem dentro dos 7 dias antes de 5/ago.
    assert quantidade == 3
    assert janela_dias == resumo._JANELA_DESTAQUE_PUBLICACOES_DIAS


def test_contagem_publicacoes_recentes_ignora_publicacao_fora_da_janela():
    df_reels = _df_reels_com_data(["2026-07-01", "2026-08-20"])

    resultado = resumo._contagem_publicacoes_recentes(
        df_reels, pd.DataFrame(), "https://www.instagram.com/gov_a/"
    )

    assert resultado is not None
    quantidade, _ = resultado
    # A janela termina em 20/ago (data mais recente); 1/jul fica muito antes
    # dos 7 dias de janela e não deve ser contada.
    assert quantidade == 1


def test_contagem_publicacoes_recentes_filtra_por_governador():
    df_reels = _df_reels_com_data(["2026-08-01"], governor_url="https://www.instagram.com/outro/")

    resultado = resumo._contagem_publicacoes_recentes(
        df_reels, pd.DataFrame(), "https://www.instagram.com/gov_a/"
    )

    assert resultado is None


def test_contagem_publicacoes_recentes_none_quando_tabelas_vazias():
    assert resumo._contagem_publicacoes_recentes(
        pd.DataFrame(), pd.DataFrame(), "https://www.instagram.com/gov_a/"
    ) is None


def test_contagem_publicacoes_recentes_none_sem_coluna_data_hora():
    df_sem_data = pd.DataFrame({"inputUrl": ["https://www.instagram.com/gov_a/"]})
    assert resumo._contagem_publicacoes_recentes(
        df_sem_data, pd.DataFrame(), "https://www.instagram.com/gov_a/"
    ) is None


# ---------------------------------------------------------------------------
# ADR 0023, user story 10: o filtro de calendário do destaque de
# negatividade NÃO pode vazar para a faixa de decisão nem para a tendência
# de engajamento/seguidores -- prova estrutural de que essas funções nunca
# ganham parâmetro de intervalo de datas.
# ---------------------------------------------------------------------------


def test_faixa_de_decisao_e_tendencia_de_engajamento_nao_aceitam_filtro_de_calendario():
    funcoes_fora_do_filtro = (
        resumo._nivel_semaforo,
        resumo._frase_decisao,
        resumo._delta_para_governador,
        resumo._contagem_publicacoes_recentes,
    )
    for fn in funcoes_fora_do_filtro:
        params = set(inspect.signature(fn).parameters)
        assert not params & {"data_inicio", "data_fim"}, fn.__name__


# ---------------------------------------------------------------------------
# Destaque 3 -- alto % positivo e baixo volume de discurso
# ---------------------------------------------------------------------------


def _df_topic_priority():
    return pd.DataFrame(
        {
            "Topic": [0, 1, 2],
            "Name": ["0_saude", "1_seguranca", "2_educacao"],
            "proporcao_sentimento_positivo": [0.9, 0.5, 0.2],
        }
    )


def test_topico_alto_positivo_baixo_discurso_escolhe_positivo_com_pouco_volume():
    df_discurso = pd.DataFrame({"Topic": [0, 0, 1, 1, 1, 1, 1]})

    resultado = resumo._topico_alto_positivo_baixo_discurso(_df_topic_priority(), df_discurso)

    assert resultado is not None
    # Tópico 0 tem % positivo alto (0.9, acima da mediana) e só 2 menções no
    # discurso -- menos do que o tópico 1 (5 menções), então vence.
    assert resultado["topic"] == 0
    assert resultado["volume_discurso"] == 2


def test_topico_alto_positivo_baixo_discurso_degrada_quando_discurso_vazio():
    resultado = resumo._topico_alto_positivo_baixo_discurso(
        _df_topic_priority(), pd.DataFrame()
    )
    assert resultado == resumo.SEM_DADO_DISCURSO


def test_topico_alto_positivo_baixo_discurso_retorna_none_sem_topic_priority():
    resultado = resumo._topico_alto_positivo_baixo_discurso(
        pd.DataFrame(), pd.DataFrame({"Topic": [0]})
    )
    assert resultado is None


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


def test_melhor_post_contra_tabelas_delta_reais(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    clusters_path = settings.GOLD_DIR / "governor_clusters"
    write_deltalake(str(clusters_path), _df_clusters_conteudo(), mode="overwrite")

    reels_path = settings.SILVER_DIR / "reels_clean"
    write_deltalake(str(reels_path), _df_reels_conteudo(), mode="overwrite")

    df_clusters = data.load_clusters_content()
    df_reels = data.load_reels_content()

    resultado = resumo._melhor_post(df_clusters, df_reels, "https://www.instagram.com/gov_a/")

    assert resultado is not None
    assert resultado["shortCode"] == "xyz"
    _clear_caches()


def test_load_reels_content_retorna_vazio_quando_silver_nao_existe(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = data.load_reels_content()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_delta_positivo_contra_tabela_delta_real_de_sentiment_history(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    history_path = settings.GOLD_DIR / "governor_sentiment_history"
    df_history = _df_sentiment_history_dois_runs().assign(fonte="comentario")
    write_deltalake(str(history_path), df_history, mode="overwrite")

    df_sentiment_history = data.comments_only(data.load_sentiment_history())
    agregado = resumo._agregar_pct_positivo_por_run(df_sentiment_history)
    resultado = resumo._delta_para_governador(
        agregado, "pct_positivo", "https://www.instagram.com/gov_a/"
    )

    assert resultado is not None
    valor_atual, _delta = resultado
    assert valor_atual == 1.0
    _clear_caches()
