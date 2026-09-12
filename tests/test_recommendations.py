import pandas as pd

from src.dashboard.recommendations import (
    check_engagement_drop,
    check_engagement_quadrant,
    check_frequency_below_cluster_peers,
    check_negative_sentiment_topic,
    check_sentiment_trend_drop,
    check_shorter_or_longer_reels_than_peers,
    check_uncovered_priority_topic,
    compute_recommendations,
)

GOV_A = "https://www.instagram.com/governador_a/"
GOV_B = "https://www.instagram.com/governador_b/"
GOV_C = "https://www.instagram.com/governador_c/"
GOV_D = "https://www.instagram.com/governador_d/"


# --- check_engagement_drop ---


def test_engagement_drop_dispara_com_queda_acima_do_limiar():
    df = pd.DataFrame(
        {
            "inputUrl": [GOV_A, GOV_A, GOV_A],
            "% ENGAJAMENTO": [10.0, 10.0, 5.0],
            "_generated_at": pd.to_datetime(["2026-05-01", "2026-05-08", "2026-05-15"], utc=True),
        }
    )
    msg = check_engagement_drop(df, GOV_A)
    assert msg is not None
    assert "caiu" in msg


def test_engagement_drop_nao_dispara_com_queda_abaixo_do_limiar():
    df = pd.DataFrame(
        {
            "inputUrl": [GOV_A, GOV_A],
            "% ENGAJAMENTO": [10.0, 9.5],
            "_generated_at": pd.to_datetime(["2026-05-01", "2026-05-08"], utc=True),
        }
    )
    assert check_engagement_drop(df, GOV_A) is None


def test_engagement_drop_nao_dispara_com_apenas_uma_execucao():
    df = pd.DataFrame(
        {
            "inputUrl": [GOV_A],
            "% ENGAJAMENTO": [5.0],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    assert check_engagement_drop(df, GOV_A) is None


def test_engagement_drop_nao_dispara_com_dataframe_vazio():
    df = pd.DataFrame(columns=["inputUrl", "% ENGAJAMENTO", "_generated_at"])
    assert check_engagement_drop(df, GOV_A) is None


# --- check_sentiment_trend_drop ---


def test_sentiment_trend_drop_dispara_com_queda_acima_do_limiar():
    df = pd.DataFrame(
        {
            "inputUrl": [GOV_A] * 4,
            "sentiment_label": ["positive", "positive", "positive", "negative"],
            "_run_id": ["r1", "r1", "r2", "r2"],
            "_generated_at": pd.to_datetime(
                ["2026-05-01", "2026-05-01", "2026-05-08", "2026-05-08"], utc=True
            ),
        }
    )
    # r1: 100% positivo, r2: 50% positivo -- queda de 50pp >= 10pp.
    msg = check_sentiment_trend_drop(df, GOV_A)
    assert msg is not None
    assert "pontos percentuais" in msg


def test_sentiment_trend_drop_nao_dispara_com_queda_pequena():
    df = pd.DataFrame(
        {
            "inputUrl": [GOV_A] * 4,
            "sentiment_label": ["positive", "negative", "positive", "positive"],
            "_run_id": ["r1", "r1", "r2", "r2"],
            "_generated_at": pd.to_datetime(
                ["2026-05-01", "2026-05-01", "2026-05-08", "2026-05-08"], utc=True
            ),
        }
    )
    # r1: 50% positivo, r2: 100% positivo -- subiu, não caiu.
    assert check_sentiment_trend_drop(df, GOV_A) is None


def test_sentiment_trend_drop_nao_dispara_com_apenas_uma_execucao():
    df = pd.DataFrame(
        {
            "inputUrl": [GOV_A],
            "sentiment_label": ["negative"],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    assert check_sentiment_trend_drop(df, GOV_A) is None


def test_sentiment_trend_drop_nao_dispara_com_dataframe_vazio():
    df = pd.DataFrame(columns=["inputUrl", "sentiment_label", "_run_id", "_generated_at"])
    assert check_sentiment_trend_drop(df, GOV_A) is None


# --- check_negative_sentiment_topic ---


def test_negative_sentiment_topic_dispara_quando_topico_concentra_negativos():
    df = pd.DataFrame(
        {
            "inputUrl": [GOV_A] * 6,
            "Name": ["saude"] * 5 + ["educacao"] * 1,
            "sentiment_label": ["negative", "negative", "negative", "positive", "negative", "positive"],
        }
    )
    # saude: 5 comentários, 4/5 = 80% negativo >= 50%.
    msg = check_negative_sentiment_topic(df, GOV_A)
    assert msg is not None
    assert "saude" in msg


def test_negative_sentiment_topic_nao_dispara_com_topico_abaixo_do_limiar():
    df = pd.DataFrame(
        {
            "inputUrl": [GOV_A] * 5,
            "Name": ["saude"] * 5,
            "sentiment_label": ["negative", "negative", "positive", "positive", "positive"],
        }
    )
    # saude: 2/5 = 40% negativo < 50%.
    assert check_negative_sentiment_topic(df, GOV_A) is None


def test_negative_sentiment_topic_ignora_topico_com_poucos_comentarios():
    df = pd.DataFrame(
        {
            "inputUrl": [GOV_A] * 2,
            "Name": ["topico_raro"] * 2,
            "sentiment_label": ["negative", "negative"],
        }
    )
    # 100% negativo, mas só 2 comentários -- abaixo de min_comentarios=5.
    assert check_negative_sentiment_topic(df, GOV_A) is None


def test_negative_sentiment_topic_nao_dispara_com_dataframe_vazio():
    df = pd.DataFrame(columns=["inputUrl", "Name", "sentiment_label"])
    assert check_negative_sentiment_topic(df, GOV_A) is None


# --- check_shorter_or_longer_reels_than_peers ---


def _df_profile_clusters():
    return pd.DataFrame(
        {
            "inputUrl": [GOV_A, GOV_B, GOV_C],
            "cluster_perfil_engajamento": [0, 0, 1],
        }
    )


def test_reels_duration_dispara_quando_mais_curtos_que_pares():
    df_reels = pd.DataFrame(
        {
            "inputUrl": [GOV_A, GOV_A, GOV_B, GOV_B],
            "videoDuration": [10.0, 10.0, 30.0, 30.0],
        }
    )
    msg = check_shorter_or_longer_reels_than_peers(df_reels, _df_profile_clusters(), GOV_A)
    assert msg is not None
    assert "mais curtos" in msg


def test_reels_duration_dispara_quando_mais_longos_que_pares():
    df_reels = pd.DataFrame(
        {
            "inputUrl": [GOV_A, GOV_A, GOV_B, GOV_B],
            "videoDuration": [30.0, 30.0, 10.0, 10.0],
        }
    )
    msg = check_shorter_or_longer_reels_than_peers(df_reels, _df_profile_clusters(), GOV_A)
    assert msg is not None
    assert "mais longos" in msg


def test_reels_duration_nao_dispara_com_duracao_similar():
    df_reels = pd.DataFrame(
        {
            "inputUrl": [GOV_A, GOV_A, GOV_B, GOV_B],
            "videoDuration": [20.0, 20.0, 21.0, 21.0],
        }
    )
    assert check_shorter_or_longer_reels_than_peers(df_reels, _df_profile_clusters(), GOV_A) is None


def test_reels_duration_nao_dispara_sem_pares_no_cluster():
    df_reels = pd.DataFrame({"inputUrl": [GOV_C], "videoDuration": [10.0]})
    # governador_c é o único do cluster 1 -- sem pares.
    assert check_shorter_or_longer_reels_than_peers(df_reels, _df_profile_clusters(), GOV_C) is None


def test_reels_duration_nao_dispara_com_dataframe_vazio():
    df_reels = pd.DataFrame(columns=["inputUrl", "videoDuration"])
    assert check_shorter_or_longer_reels_than_peers(df_reels, _df_profile_clusters(), GOV_A) is None


# --- check_frequency_below_cluster_peers ---


def test_frequency_below_peers_dispara_quando_abaixo_do_limiar():
    df_engagement = pd.DataFrame(
        {
            "inputUrl": [GOV_A, GOV_B],
            "FREQUENCIA": [1.0, 2.0],
        }
    )
    msg = check_frequency_below_cluster_peers(df_engagement, _df_profile_clusters(), GOV_A)
    # 1.0 vs média dos pares (2.0) -- 50% abaixo, >= limiar de 20%.
    assert msg is not None
    assert "abaixo da média" in msg


def test_frequency_below_peers_nao_dispara_quando_acima_dos_pares():
    df_engagement = pd.DataFrame(
        {
            "inputUrl": [GOV_A, GOV_B],
            "FREQUENCIA": [3.0, 2.0],
        }
    )
    assert check_frequency_below_cluster_peers(df_engagement, _df_profile_clusters(), GOV_A) is None


def test_frequency_below_peers_nao_dispara_sem_pares_no_cluster():
    df_engagement = pd.DataFrame({"inputUrl": [GOV_C], "FREQUENCIA": [0.1]})
    assert check_frequency_below_cluster_peers(df_engagement, _df_profile_clusters(), GOV_C) is None


def test_frequency_below_peers_nao_dispara_com_dataframe_vazio():
    df_engagement = pd.DataFrame(columns=["inputUrl", "FREQUENCIA"])
    assert check_frequency_below_cluster_peers(df_engagement, _df_profile_clusters(), GOV_A) is None


# --- check_engagement_quadrant (ADR 0018) ---


def _df_quadrantes_engagement():
    """Mesma configuração de test_comparisons.py::_df_quadrantes -- um
    governador em cada quadrante, mais um exatamente na mediana dos dois
    eixos (mediana de followersCount é 500, de % ENGAJAMENTO é 0.05)."""
    return pd.DataFrame(
        {
            "inputUrl": [GOV_A, GOV_B, "https://www.instagram.com/mediano/", GOV_C, GOV_D],
            "followersCount": [100, 900, 500, 200, 800],
            "% ENGAJAMENTO": [0.01, 0.02, 0.05, 0.20, 0.30],
        }
    )


def test_engagement_quadrant_inexpressivo():
    msg = check_engagement_quadrant(_df_quadrantes_engagement(), GOV_A)
    assert msg is not None
    assert "Inexpressivo" in msg


def test_engagement_quadrant_gigante_adormecido():
    msg = check_engagement_quadrant(_df_quadrantes_engagement(), GOV_B)
    assert msg is not None
    assert "Gigante Adormecido" in msg


def test_engagement_quadrant_nicho():
    msg = check_engagement_quadrant(_df_quadrantes_engagement(), GOV_C)
    assert msg is not None
    assert "Nicho" in msg


def test_engagement_quadrant_superstar():
    msg = check_engagement_quadrant(_df_quadrantes_engagement(), GOV_D)
    assert msg is not None
    assert "Superstar" in msg


def test_engagement_quadrant_dado_insuficiente_retorna_none():
    df = pd.DataFrame({"inputUrl": [GOV_A], "followersCount": [100], "% ENGAJAMENTO": [0.01]})
    assert check_engagement_quadrant(df, GOV_A) is None


def test_engagement_quadrant_sem_colunas_necessarias_retorna_none():
    df = pd.DataFrame({"inputUrl": [GOV_A, GOV_B], "FREQUENCIA": [1.0, 2.0]})
    assert check_engagement_quadrant(df, GOV_A) is None


def test_engagement_quadrant_governador_nao_encontrado_retorna_none():
    msg = check_engagement_quadrant(
        _df_quadrantes_engagement(), "https://www.instagram.com/nao_existe/"
    )
    assert msg is None


# --- compute_recommendations ---


def test_compute_recommendations_agrega_regras_disparadas_na_ordem():
    df_engagement = pd.DataFrame({"inputUrl": [GOV_A, GOV_B], "FREQUENCIA": [1.0, 2.0]})
    df_engagement_history = pd.DataFrame(
        {
            "inputUrl": [GOV_A, GOV_A],
            "% ENGAJAMENTO": [10.0, 5.0],
            "_generated_at": pd.to_datetime(["2026-05-01", "2026-05-08"], utc=True),
        }
    )
    df_sentiment = pd.DataFrame(columns=["inputUrl", "Name", "sentiment_label"])
    df_sentiment_history = pd.DataFrame(
        columns=["inputUrl", "sentiment_label", "_run_id", "_generated_at"]
    )
    df_reels = pd.DataFrame(columns=["inputUrl", "videoDuration"])
    df_profile_clusters = _df_profile_clusters()

    achados = compute_recommendations(
        GOV_A,
        df_engagement,
        df_engagement_history,
        df_sentiment,
        df_sentiment_history,
        df_reels,
        df_profile_clusters,
    )
    # Só engagement_drop (dado suficiente) e frequency_below_peers devem disparar.
    assert len(achados) == 2
    assert "caiu" in achados[0]
    assert "abaixo da média" in achados[1]


def test_compute_recommendations_inclui_achado_de_quadrante_quando_ha_dado():
    """check_engagement_quadrant é a 6ª regra da lista -- com followersCount/
    % ENGAJAMENTO suficientes em df_engagement, o achado de quadrante entra
    junto dos demais."""
    df_engagement = _df_quadrantes_engagement().assign(FREQUENCIA=1.0)
    df_engagement_history = pd.DataFrame(columns=["inputUrl", "% ENGAJAMENTO", "_generated_at"])
    df_sentiment = pd.DataFrame(columns=["inputUrl", "Name", "sentiment_label"])
    df_sentiment_history = pd.DataFrame(
        columns=["inputUrl", "sentiment_label", "_run_id", "_generated_at"]
    )
    df_reels = pd.DataFrame(columns=["inputUrl", "videoDuration"])
    df_profile_clusters = pd.DataFrame(columns=["inputUrl", "cluster_perfil_engajamento"])

    achados = compute_recommendations(
        GOV_A,
        df_engagement,
        df_engagement_history,
        df_sentiment,
        df_sentiment_history,
        df_reels,
        df_profile_clusters,
    )
    assert any("Inexpressivo" in achado for achado in achados)


def test_compute_recommendations_retorna_lista_vazia_sem_nenhum_disparo():
    df_engagement = pd.DataFrame(columns=["inputUrl", "FREQUENCIA"])
    df_engagement_history = pd.DataFrame(columns=["inputUrl", "% ENGAJAMENTO", "_generated_at"])
    df_sentiment = pd.DataFrame(columns=["inputUrl", "Name", "sentiment_label"])
    df_sentiment_history = pd.DataFrame(
        columns=["inputUrl", "sentiment_label", "_run_id", "_generated_at"]
    )
    df_reels = pd.DataFrame(columns=["inputUrl", "videoDuration"])
    df_profile_clusters = pd.DataFrame(columns=["inputUrl", "cluster_perfil_engajamento"])

    achados = compute_recommendations(
        GOV_A,
        df_engagement,
        df_engagement_history,
        df_sentiment,
        df_sentiment_history,
        df_reels,
        df_profile_clusters,
    )
    assert achados == []


# --- check_uncovered_priority_topic (ADR 0020 / issue #94) ---


def _df_topic_priority():
    return pd.DataFrame(
        {
            "Topic": [3, 7, 12],
            "Name": ["3_seguranca", "7_saude", "12_educacao"],
            "score": [0.9, 0.7, 0.5],
        }
    )


def test_uncovered_priority_topic_dispara_com_tema_top_nao_coberto():
    df_discourse = pd.DataFrame(
        {
            "inputUrl": [GOV_A],
            "Name": ["7_saude"],
        }
    )
    msg = check_uncovered_priority_topic(_df_topic_priority(), df_discourse, GOV_A)

    assert msg is not None
    # "3_seguranca" é o de maior score (0.9) entre os não cobertos -- deve
    # ser o citado, não "7_saude" (que o governador já cobriu) nem
    # "12_educacao" (menor score entre os não cobertos).
    assert "3_seguranca" in msg


def test_uncovered_priority_topic_nao_dispara_quando_todos_os_temas_top_ja_cobertos():
    df_discourse = pd.DataFrame(
        {
            "inputUrl": [GOV_A, GOV_A, GOV_A],
            "Name": ["3_seguranca", "7_saude", "12_educacao"],
        }
    )
    msg = check_uncovered_priority_topic(_df_topic_priority(), df_discourse, GOV_A)
    assert msg is None


def test_uncovered_priority_topic_ignora_cobertura_de_outro_governador():
    """`governor_discourse_topics` de OUTRO governador não deve contar como
    "coberto" para o governador selecionado -- cada um só cobre o próprio
    discurso."""
    df_discourse = pd.DataFrame(
        {
            "inputUrl": [GOV_B, GOV_B, GOV_B],
            "Name": ["3_seguranca", "7_saude", "12_educacao"],
        }
    )
    msg = check_uncovered_priority_topic(_df_topic_priority(), df_discourse, GOV_A)

    assert msg is not None
    assert "3_seguranca" in msg


def test_uncovered_priority_topic_none_sem_topic_priority_score():
    df_discourse = pd.DataFrame({"inputUrl": [GOV_A], "Name": ["3_seguranca"]})
    msg = check_uncovered_priority_topic(pd.DataFrame(), df_discourse, GOV_A)
    assert msg is None


def test_uncovered_priority_topic_none_sem_discourse_topics():
    msg = check_uncovered_priority_topic(_df_topic_priority(), pd.DataFrame(), GOV_A)
    assert msg is None


def test_compute_recommendations_dispara_tema_nao_abordado_quando_tabelas_passadas():
    df_engagement = pd.DataFrame(columns=["inputUrl", "FREQUENCIA"])
    df_engagement_history = pd.DataFrame(columns=["inputUrl", "% ENGAJAMENTO", "_generated_at"])
    df_sentiment = pd.DataFrame(columns=["inputUrl", "Name", "sentiment_label"])
    df_sentiment_history = pd.DataFrame(
        columns=["inputUrl", "sentiment_label", "_run_id", "_generated_at"]
    )
    df_reels = pd.DataFrame(columns=["inputUrl", "videoDuration"])
    df_profile_clusters = pd.DataFrame(columns=["inputUrl", "cluster_perfil_engajamento"])
    df_discourse = pd.DataFrame({"inputUrl": [GOV_A], "Name": ["7_saude"]})

    achados = compute_recommendations(
        GOV_A,
        df_engagement,
        df_engagement_history,
        df_sentiment,
        df_sentiment_history,
        df_reels,
        df_profile_clusters,
        df_topic_priority=_df_topic_priority(),
        df_discourse_topics=df_discourse,
    )
    assert any("3_seguranca" in achado for achado in achados)


def test_compute_recommendations_sem_tabelas_de_topico_nao_quebra():
    """Chamadas antigas (antes da issue #94), sem os dois parâmetros novos,
    continuam funcionando -- a regra de tema não abordado só não dispara."""
    df_engagement = pd.DataFrame(columns=["inputUrl", "FREQUENCIA"])
    df_engagement_history = pd.DataFrame(columns=["inputUrl", "% ENGAJAMENTO", "_generated_at"])
    df_sentiment = pd.DataFrame(columns=["inputUrl", "Name", "sentiment_label"])
    df_sentiment_history = pd.DataFrame(
        columns=["inputUrl", "sentiment_label", "_run_id", "_generated_at"]
    )
    df_reels = pd.DataFrame(columns=["inputUrl", "videoDuration"])
    df_profile_clusters = pd.DataFrame(columns=["inputUrl", "cluster_perfil_engajamento"])

    achados = compute_recommendations(
        GOV_A,
        df_engagement,
        df_engagement_history,
        df_sentiment,
        df_sentiment_history,
        df_reels,
        df_profile_clusters,
    )
    assert achados == []
