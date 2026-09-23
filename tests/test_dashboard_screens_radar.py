"""Testes da Tela 3 ("Radar de crise", ADR 0021 / issue #113).

Só a lógica pura de `dashboard/screens/radar.py` é testada aqui (nível do
semáforo, agregações, seleção do tema em maior ascensão, lista de
comentários) -- nunca a renderização Streamlit em si, mesmo padrão de
`tests/test_dashboard_screens_resumo.py`/`test_dashboard_screens_produzir.py`
(issue #111/#112). Um bloco final testa alguns desses caminhos contra
tabelas Delta reais escritas em `tmp_path`, mesmo padrão dos dois arquivos
acima.

O teste `test_comentarios_negativos_recentes_nunca_expoe_autor` abaixo é
NÃO-NEGOCIÁVEL (issue #113, user story 5) -- prova que a lista de comentários
nunca vaza `ownerUsername` (ou qualquer outra coluna de identidade), mesmo
que a tabela de origem tenha a coluna. Não remover nem enfraquecer.
"""

import datetime
import inspect

import pandas as pd
import streamlit as st
from deltalake.writer import write_deltalake

from config import settings
from dashboard.core import data
from dashboard.core.deltas import (
    LIMIAR_NEGATIVIDADE_ALERTA,
    aggregate_pct_negative_by_publication_day,
)
from dashboard.screens import radar


def _clear_caches():
    st.cache_resource.clear()
    st.cache_data.clear()


def _point_settings_at(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "GOLD_DIR", tmp_path / "gold")
    monkeypatch.setattr(settings, "SILVER_DIR", tmp_path / "silver")
    _clear_caches()


# ---------------------------------------------------------------------------
# _nivel_semaforo (frase de decisão) -- issue #113, Testing Decisions: os 3
# casos (cruzou / subiu sem cruzar / estável) + o caso "sem comentários
# negativos" -> verde "sem alertas hoje".
# ---------------------------------------------------------------------------


def test_nivel_semaforo_vermelho_quando_cruza_limiar():
    nivel = radar._nivel_semaforo(pct_negativo_atual=0.40, delta_percentual=150.0)
    assert nivel == "danger"


def test_nivel_semaforo_vermelho_no_limiar_exato():
    nivel = radar._nivel_semaforo(
        pct_negativo_atual=LIMIAR_NEGATIVIDADE_ALERTA, delta_percentual=1.0
    )
    assert nivel == "danger"


def test_nivel_semaforo_amarelo_quando_sobe_sem_cruzar():
    nivel = radar._nivel_semaforo(pct_negativo_atual=0.20, delta_percentual=50.0)
    assert nivel == "warn"


def test_nivel_semaforo_verde_quando_estavel_ou_caindo():
    assert radar._nivel_semaforo(pct_negativo_atual=0.20, delta_percentual=-10.0) == "good"
    assert radar._nivel_semaforo(pct_negativo_atual=0.20, delta_percentual=0.0) == "good"
    assert radar._nivel_semaforo(pct_negativo_atual=0.20, delta_percentual=None) == "good"


def test_nivel_semaforo_verde_sem_alertas_quando_nao_ha_comentario_negativo():
    # "Sem comentários negativos suficientes para preocupar" -- nunca um
    # estado neutro/confuso, sempre "sem alertas hoje" em verde (user story 7).
    nivel = radar._nivel_semaforo(pct_negativo_atual=None, delta_percentual=None)
    assert nivel == "good"


def test_nivel_semaforo_respeita_limiar_customizado():
    nivel = radar._nivel_semaforo(pct_negativo_atual=0.25, delta_percentual=10.0, limiar=0.20)
    assert nivel == "danger"


# ---------------------------------------------------------------------------
# _filtrar_por_intervalo / _quebrar_em_segmentos (linha do tempo, ADR 0023 --
# substitui a antiga agregação por execução, issue #113)
# ---------------------------------------------------------------------------


def _df_timeline_publicacao():
    return pd.DataFrame(
        {
            "data": [
                datetime.date(2026, 8, 1),
                datetime.date(2026, 8, 3),
                datetime.date(2026, 8, 20),
            ],
            "pct_negativo": [0.10, 0.50, 0.90],
        }
    )


def test_filtrar_por_intervalo_restringe_ao_periodo_escolhido():
    resultado = radar._filtrar_por_intervalo(
        _df_timeline_publicacao(), datetime.date(2026, 8, 1), datetime.date(2026, 8, 3)
    )
    assert resultado["data"].tolist() == [datetime.date(2026, 8, 1), datetime.date(2026, 8, 3)]


def test_filtrar_por_intervalo_sem_limites_retorna_tudo():
    resultado = radar._filtrar_por_intervalo(_df_timeline_publicacao(), None, None)
    assert len(resultado) == 3


def test_filtrar_por_intervalo_com_dataframe_vazio():
    resultado = radar._filtrar_por_intervalo(
        pd.DataFrame(columns=["data", "pct_negativo"]), None, None
    )
    assert resultado.empty


# `_quebrar_em_segmentos` foi extraída pra `dashboard/core/deltas.py`
# (`quebrar_em_segmentos`) pela ADR 0024, quando ganhou um segundo
# consumidor real (a seção de evidência de desempenho de `produzir.py`) --
# ver `tests/test_dashboard_core_deltas.py` pelos testes correspondentes.

# ---------------------------------------------------------------------------
# _cores_marcador (ADR 0023 -- só o ponto que cruza o limiar é marcado,
# nunca o segmento da linha inteiro)
# ---------------------------------------------------------------------------


def test_cores_marcador_vermelho_no_ponto_que_cruza_o_limiar():
    cores = radar._cores_marcador(pd.Series([10.0, 35.0, 20.0]), limiar_pct=30.0)
    assert cores == [
        radar.COLORS["muted"],
        radar.COLORS["danger"]["fg"],
        radar.COLORS["muted"],
    ]


def test_cores_marcador_vermelho_no_limiar_exato():
    cores = radar._cores_marcador(pd.Series([30.0]), limiar_pct=30.0)
    assert cores == [radar.COLORS["danger"]["fg"]]


def test_cores_marcador_lista_vazia_com_serie_vazia():
    assert radar._cores_marcador(pd.Series([], dtype=float), limiar_pct=30.0) == []


# ---------------------------------------------------------------------------
# ADR 0023, user story 8: o filtro de calendário da linha do tempo NÃO pode
# vazar para a frase de decisão nem para a lista de comentários -- prova
# estrutural de que essas funções nunca ganham parâmetro de intervalo de
# datas (se ganhassem, seria sinal de que o filtro vazou pra fora do
# gráfico).
# ---------------------------------------------------------------------------


def test_frase_decisao_e_lista_de_comentarios_nao_aceitam_filtro_de_calendario():
    funcoes_fora_do_filtro = (
        radar._nivel_semaforo,
        radar._tema_maior_alta_negatividade,
        radar._frase_decisao,
        radar._comentarios_negativos_recentes,
    )
    for fn in funcoes_fora_do_filtro:
        params = set(inspect.signature(fn).parameters)
        assert not params & {"data_inicio", "data_fim"}, fn.__name__


# ---------------------------------------------------------------------------
# _tema_maior_alta_negatividade (tema em maior ascensão de negatividade --
# ADR 0025 / issue #153: janela de 7 dias por data de publicação, não mais
# por execução via `week_over_week`)
# ---------------------------------------------------------------------------


def _df_sentiment_history_bruto_com_alta():
    # Âncora = 2026-09-08 (maior data). Janela atual (7 dias, padrão) =
    # [09-02, 09-08]; janela anterior = [08-26, 09-01] -- coincide com as
    # datas de publicação abaixo (09-01/09-08), então o resultado é
    # equivalente ao antigo critério por execução para este fixture.
    return pd.DataFrame(
        {
            "id_comment": [f"c{i}" for i in range(8)],
            "Topic": [1, 1, 1, 1, 2, 2, 2, 2],
            "Name": ["Segurança pública"] * 4 + ["Saúde"] * 4,
            "sentiment_label": [
                "negative",
                "positive",
                "negative",
                "negative",
                "negative",
                "negative",
                "negative",
                "negative",
            ],
            "_run_id": ["run_1", "run_1", "run_2", "run_2", "run_1", "run_1", "run_2", "run_2"],
            "timestamp": [
                "2026-09-01T10:00:00.000Z",
                "2026-09-01T10:05:00.000Z",
                "2026-09-08T10:00:00.000Z",
                "2026-09-08T10:05:00.000Z",
                "2026-09-01T11:00:00.000Z",
                "2026-09-01T11:05:00.000Z",
                "2026-09-08T11:00:00.000Z",
                "2026-09-08T11:05:00.000Z",
            ],
        }
    )


def test_tema_maior_alta_negatividade_escolhe_maior_delta_positivo():
    resultado = radar._tema_maior_alta_negatividade(_df_sentiment_history_bruto_com_alta())
    assert resultado is not None
    assert resultado["topic"] == 1
    assert resultado["name"] == "Segurança pública"
    assert resultado["pct_atual"] == 1.0
    assert resultado["pct_anterior"] == 0.5
    assert resultado["delta_percentual"] > 0


def test_tema_maior_alta_negatividade_none_quando_todos_estaveis_ou_caindo():
    df = pd.DataFrame(
        {
            "id_comment": ["c1", "c2"],
            "Topic": [2, 2],
            "Name": ["Saúde", "Saúde"],
            "sentiment_label": ["negative", "negative"],
            "_run_id": ["run_1", "run_2"],
            "timestamp": ["2026-09-01T10:00:00.000Z", "2026-09-08T10:00:00.000Z"],
        }
    )
    assert radar._tema_maior_alta_negatividade(df) is None


def test_tema_maior_alta_negatividade_none_com_historico_insuficiente():
    # Só a janela atual tem dado publicado -- sem janela anterior pra
    # comparar, delta degrada para None (nunca vira "alta" fabricada).
    df = pd.DataFrame(
        {
            "id_comment": ["c1"],
            "Topic": [1],
            "Name": ["Segurança pública"],
            "sentiment_label": ["negative"],
            "_run_id": ["run_1"],
            "timestamp": ["2026-09-08T10:00:00.000Z"],
        }
    )
    assert radar._tema_maior_alta_negatividade(df) is None


def test_tema_maior_alta_negatividade_none_com_dataframe_vazio():
    assert radar._tema_maior_alta_negatividade(pd.DataFrame()) is None


# ---------------------------------------------------------------------------
# _maior_alta_negatividade -- 2ª leitura exploratória por período livre (ADR
# 0026 / issue #154), portada sem mudança de comportamento de
# resumo.py::_maior_alta_negatividade (ver docstring da função). DIFERENTE
# de `_tema_maior_alta_negatividade` acima (essa é a janela fixa do alerta
# principal).
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
    resultado = radar._maior_alta_negatividade(_df_sentiment_history_topicos_por_publicacao())

    assert resultado is not None
    assert resultado["topic"] == 0
    assert resultado["name"] == "0_saude"
    assert resultado["pct_negativo"] == 75.0


def test_maior_alta_negatividade_respeita_filtro_de_intervalo():
    df = _df_sentiment_history_topicos_por_publicacao()

    # Restringindo ao dia 4/ago só: nenhum tópico com negatividade > 0 nesse
    # recorte (ambos só têm comentário positivo em 4/ago) -- prova que o
    # filtro de fato altera o dado agregado, não só decora a chamada.
    resultado_periodo_completo = radar._maior_alta_negatividade(df)
    resultado_um_dia = radar._maior_alta_negatividade(
        df, data_inicio=datetime.date(2026, 8, 4), data_fim=datetime.date(2026, 8, 4)
    )

    assert resultado_periodo_completo["topic"] == 0
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
    resultado = radar._maior_alta_negatividade(df)

    assert resultado is not None
    assert resultado["pct_negativo"] == 100.0


def test_maior_alta_negatividade_retorna_none_sem_topico_atribuido():
    df = _df_sentiment_history_topicos_por_publicacao()
    df["Topic"] = None
    assert radar._maior_alta_negatividade(df) is None


def test_maior_alta_negatividade_retorna_none_quando_nenhum_topico_tem_negatividade():
    df = _df_sentiment_history_topicos_por_publicacao()
    df["sentiment_label"] = "positive"
    assert radar._maior_alta_negatividade(df) is None


def test_maior_alta_negatividade_retorna_none_para_dataframe_vazio():
    assert radar._maior_alta_negatividade(pd.DataFrame()) is None


# ---------------------------------------------------------------------------
# _frase_decisao
# ---------------------------------------------------------------------------


def test_frase_decisao_sem_tema_em_alta():
    texto = radar._frase_decisao("good", None)
    assert "Sem alertas hoje" in texto


def test_frase_decisao_vermelho_menciona_nome_do_tema_e_percentuais_arredondados():
    tema = {
        "topic": 1,
        "name": "Segurança pública",
        "pct_atual": 0.343,
        "pct_anterior": 0.181,
        "delta_percentual": 89.5,
    }
    texto = radar._frase_decisao("danger", tema)
    assert "Segurança pública" in texto
    assert "18%" in texto
    assert "34%" in texto


# ---------------------------------------------------------------------------
# _comentarios_negativos_recentes -- lista de comentários negativos
# ---------------------------------------------------------------------------


def test_comentarios_negativos_recentes_ordena_por_mais_recente():
    df = pd.DataFrame(
        {
            "text": ["mais antigo", "mais recente"],
            "sentiment_label": ["negative", "negative"],
            "Topic": [1, 1],
            "Name": ["Segurança pública", "Segurança pública"],
            "_run_id": ["run_1", "run_2"],
            "_generated_at": pd.to_datetime(["2026-09-01", "2026-09-08"]),
        }
    )
    resultado = radar._comentarios_negativos_recentes(df, pd.DataFrame(), topico_alvo=1)
    assert resultado["comentario"].tolist() == ["mais recente", "mais antigo"]


def test_comentarios_negativos_recentes_filtra_por_topico_alvo():
    df = pd.DataFrame(
        {
            "text": ["sobre segurança", "sobre saúde"],
            "sentiment_label": ["negative", "negative"],
            "Topic": [1, 2],
            "Name": ["Segurança pública", "Saúde"],
            "_run_id": ["run_1", "run_1"],
        }
    )
    resultado = radar._comentarios_negativos_recentes(df, pd.DataFrame(), topico_alvo=1)
    assert resultado["comentario"].tolist() == ["sobre segurança"]


def test_comentarios_negativos_recentes_ignora_comentarios_positivos():
    df = pd.DataFrame(
        {
            "text": ["negativo", "positivo"],
            "sentiment_label": ["negative", "positive"],
            "Topic": [1, 1],
            "Name": ["Segurança pública", "Segurança pública"],
            "_run_id": ["run_1", "run_1"],
        }
    )
    resultado = radar._comentarios_negativos_recentes(df, pd.DataFrame(), topico_alvo=None)
    assert resultado["comentario"].tolist() == ["negativo"]


def test_comentarios_negativos_recentes_cruza_com_topic_priority_quando_name_ausente():
    df = pd.DataFrame(
        {
            "text": ["tema sem nome na própria tabela"],
            "sentiment_label": ["negative"],
            "Topic": [3],
            "_run_id": ["run_1"],
        }
    )
    df_topic_priority = pd.DataFrame({"Topic": [3], "Name": ["Educação"]})
    resultado = radar._comentarios_negativos_recentes(df, df_topic_priority, topico_alvo=None)
    assert resultado["tema"].iloc[0] == "Educação"


def test_comentarios_negativos_recentes_vazio_sem_coluna_obrigatoria():
    resultado = radar._comentarios_negativos_recentes(
        pd.DataFrame({"sentiment_label": ["negative"]}), pd.DataFrame(), topico_alvo=None
    )
    assert resultado.empty
    assert list(resultado.columns) == ["comentario", "tema"]


def test_comentarios_negativos_recentes_nunca_expoe_autor():
    """NÃO-NEGOCIÁVEL (issue #113, user story 5): a lista de comentários
    NUNCA mostra nome/usuário/qualquer dado pessoal de quem comentou, mesmo
    que a tabela de origem (`governor_sentiment`) tenha a coluna
    `ownerUsername`. Teste explícito pedido pela issue -- não remover nem
    enfraquecer este teste."""
    df_sentiment = pd.DataFrame(
        {
            "text": ["comentário negativo 1", "comentário negativo 2"],
            "sentiment_label": ["negative", "negative"],
            "Topic": [1, 1],
            "Name": ["Segurança pública", "Segurança pública"],
            "_run_id": ["run_2", "run_2"],
            "_generated_at": pd.to_datetime(["2026-09-10", "2026-09-11"]),
            # Coluna de identidade real, presente na tabela de origem --
            # NUNCA deve aparecer no resultado retornado.
            "ownerUsername": ["usuario_real_1", "usuario_real_2"],
        }
    )
    df_topic_priority = pd.DataFrame(columns=["Topic", "Name"])

    resultado = radar._comentarios_negativos_recentes(
        df_sentiment, df_topic_priority, topico_alvo=1
    )

    assert "ownerUsername" not in resultado.columns
    assert set(resultado.columns) == {"comentario", "tema"}

    conteudo_serializado = str(resultado.astype(str).to_numpy().tolist())
    assert "usuario_real_1" not in conteudo_serializado
    assert "usuario_real_2" not in conteudo_serializado
    assert "ownerUsername" not in conteudo_serializado


# ---------------------------------------------------------------------------
# Governador (seleção / normalização de URL) -- mesmo padrão de
# `resumo.py`/`produzir.py`.
# ---------------------------------------------------------------------------


def test_governor_options_mapeia_nome_para_input_url():
    df_metadata = pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/gov_b/", "https://www.instagram.com/gov_a/"],
            "nome": ["Governador B", "Governador A"],
        }
    )
    opcoes = radar._governor_options(df_metadata)
    assert opcoes == {
        "Governador A": "https://www.instagram.com/gov_a/",
        "Governador B": "https://www.instagram.com/gov_b/",
    }


def test_filtrar_por_governador_normaliza_barra_final_e_caixa():
    df = pd.DataFrame({"inputUrl": ["HTTPS://www.instagram.com/gov_a"]})
    filtrado = radar._filtrar_por_governador(df, "https://www.instagram.com/gov_a/")
    assert len(filtrado) == 1


# ---------------------------------------------------------------------------
# Contra tabelas Delta reais (tmp_path) -- mesmo padrão de
# tests/test_dashboard_core_data.py / test_dashboard_loaders.py (issue #50)
# ---------------------------------------------------------------------------


def _df_sentiment_history_dois_runs_dois_temas():
    return pd.DataFrame(
        {
            "id_comment": [f"c{i}" for i in range(8)],
            "text": [f"comentário {i}" for i in range(8)],
            "inputUrl": ["https://www.instagram.com/gov_a/"] * 8,
            "ownerUsername": [f"usuario_{i}" for i in range(8)],
            "sentiment_label": [
                "negative",
                "positive",
                "negative",
                "negative",
                "negative",
                "negative",
                "negative",
                "negative",
            ],
            "Topic": [1, 1, 1, 1, 2, 2, 2, 2],
            "Name": ["Segurança pública"] * 4 + ["Saúde"] * 4,
            "_run_id": ["run_1", "run_1", "run_2", "run_2", "run_1", "run_1", "run_2", "run_2"],
            "_generated_at": pd.to_datetime(
                [
                    "2026-09-01",
                    "2026-09-01",
                    "2026-09-08",
                    "2026-09-08",
                    "2026-09-01",
                    "2026-09-01",
                    "2026-09-08",
                    "2026-09-08",
                ]
            ),
            # Data real de publicação do comentário (ADR 0023) -- distinta de
            # `_generated_at` (data da coleta), embora coincida neste fixture.
            "timestamp": [
                "2026-09-01T10:00:00.000Z",
                "2026-09-01T10:05:00.000Z",
                "2026-09-08T10:00:00.000Z",
                "2026-09-08T10:05:00.000Z",
                "2026-09-01T11:00:00.000Z",
                "2026-09-01T11:05:00.000Z",
                "2026-09-08T11:00:00.000Z",
                "2026-09-08T11:05:00.000Z",
            ],
            "fonte": ["comentario"] * 8,
        }
    )


def test_radar_contra_tabela_delta_real_de_sentiment_history(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    history_path = settings.GOLD_DIR / "governor_sentiment_history"
    write_deltalake(str(history_path), _df_sentiment_history_dois_runs_dois_temas(), mode="overwrite")

    df_history_governador = radar._filtrar_por_governador(
        data.comments_only(data.load_sentiment_history()),
        "https://www.instagram.com/gov_a/",
    )
    tema_em_alta = radar._tema_maior_alta_negatividade(df_history_governador)

    # Topic 1 (Segurança pública): 1/2 negativo no run_1 -> 1.0 no run_2
    # (alta). Topic 2 (Saúde): 1.0 negativo nos dois runs (estável) --
    # o tema em alta deve ser o 1, nunca o 2.
    assert tema_em_alta is not None
    assert tema_em_alta["topic"] == 1

    df_timeline = aggregate_pct_negative_by_publication_day(df_history_governador)
    assert not df_timeline.empty
    assert set(df_timeline["data"]) == {datetime.date(2026, 9, 1), datetime.date(2026, 9, 8)}
    _clear_caches()


def test_radar_lista_de_comentarios_contra_tabela_delta_real_nunca_expoe_autor(
    tmp_path, monkeypatch
):
    _point_settings_at(monkeypatch, tmp_path)

    sentiment_path = settings.GOLD_DIR / "governor_sentiment"
    write_deltalake(
        str(sentiment_path), _df_sentiment_history_dois_runs_dois_temas(), mode="overwrite"
    )

    df_sentiment_governador = radar._filtrar_por_governador(
        data.comments_only(data.load_sentiment()), "https://www.instagram.com/gov_a/"
    )
    resultado = radar._comentarios_negativos_recentes(
        df_sentiment_governador, pd.DataFrame(), topico_alvo=1
    )

    assert not resultado.empty
    assert "ownerUsername" not in resultado.columns
    conteudo_serializado = str(resultado.astype(str).to_numpy().tolist())
    assert "usuario_" not in conteudo_serializado
    _clear_caches()
