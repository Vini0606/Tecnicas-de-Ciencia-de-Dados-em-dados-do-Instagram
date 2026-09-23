import datetime

import pandas as pd

from dashboard.core.deltas import (
    aggregate_metric_by_publication_day,
    aggregate_pct_negative_by_publication_day,
    deduplicate_by_first_seen,
    filter_by_date_range,
    normalize_date_input_range,
    parse_publication_dates,
    quebrar_em_segmentos,
    run_dates,
    week_over_week,
)


def _df_history_two_runs():
    return pd.DataFrame(
        {
            "inputUrl": ["a", "b", "a", "b"],
            "TOTAL ENGAJAMENTO": [100, 0, 150, 10],
            "_run_id": ["r1", "r1", "r2", "r2"],
            "_generated_at": pd.to_datetime(
                ["2026-05-01", "2026-05-01", "2026-05-08", "2026-05-08"], utc=True
            ),
        }
    )


def test_week_over_week_computes_percent_delta_with_two_runs():
    df_history = _df_history_two_runs()

    resultado = week_over_week(df_history, value_col="TOTAL ENGAJAMENTO")

    assert resultado is not None
    valor_atual_a, delta_a = resultado["a"]
    assert valor_atual_a == 150
    assert delta_a == 50.0


def test_week_over_week_handles_division_by_zero_without_raising():
    df_history = _df_history_two_runs()

    resultado = week_over_week(df_history, value_col="TOTAL ENGAJAMENTO")

    assert resultado is not None
    valor_atual_b, delta_b = resultado["b"]
    assert valor_atual_b == 10
    assert delta_b is None


def test_week_over_week_returns_none_with_only_one_run():
    df_history = pd.DataFrame(
        {
            "inputUrl": ["a", "b"],
            "TOTAL ENGAJAMENTO": [100, 50],
            "_run_id": ["r1", "r1"],
            "_generated_at": pd.to_datetime(["2026-05-01", "2026-05-01"], utc=True),
        }
    )

    resultado = week_over_week(df_history, value_col="TOTAL ENGAJAMENTO")

    assert resultado is None


def test_week_over_week_returns_none_when_history_is_empty():
    df_history = pd.DataFrame(columns=["inputUrl", "TOTAL ENGAJAMENTO", "_run_id"])

    resultado = week_over_week(df_history, value_col="TOTAL ENGAJAMENTO")

    assert resultado is None


def test_run_dates_returns_previous_and_current_in_order():
    df_history = _df_history_two_runs()

    datas = run_dates(df_history)

    assert datas is not None
    anterior, atual = datas
    assert anterior == pd.Timestamp("2026-05-01", tz="UTC")
    assert atual == pd.Timestamp("2026-05-08", tz="UTC")


def test_run_dates_returns_none_with_only_one_run():
    df_history = pd.DataFrame(
        {
            "inputUrl": ["a"],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )

    datas = run_dates(df_history)

    assert datas is None


# ---------------------------------------------------------------------------
# deduplicate_by_first_seen (ADR 0023)
# ---------------------------------------------------------------------------


def test_deduplicate_by_first_seen_keeps_lowest_run_id():
    df_history = pd.DataFrame(
        {
            "id_comment": ["c1", "c1", "c2"],
            "sentiment_label": ["negative", "positive", "negative"],
            "_run_id": ["r2", "r1", "r1"],
        }
    )

    resultado = deduplicate_by_first_seen(df_history)

    linha_c1 = resultado[resultado["id_comment"] == "c1"]
    assert len(linha_c1) == 1
    assert linha_c1["_run_id"].iloc[0] == "r1"
    assert linha_c1["sentiment_label"].iloc[0] == "positive"
    assert len(resultado) == 2


def test_deduplicate_by_first_seen_returns_original_when_columns_missing():
    df_history = pd.DataFrame({"sentiment_label": ["negative"]})

    resultado = deduplicate_by_first_seen(df_history)

    pd.testing.assert_frame_equal(resultado, df_history)


def test_deduplicate_by_first_seen_returns_empty_df_unchanged():
    df_history = pd.DataFrame(columns=["id_comment", "_run_id"])

    resultado = deduplicate_by_first_seen(df_history)

    assert resultado.empty


# ---------------------------------------------------------------------------
# aggregate_pct_negative_by_publication_day (ADR 0023)
# ---------------------------------------------------------------------------


def test_aggregate_pct_negative_by_publication_day_does_not_double_count_recollected_comment():
    df_history = pd.DataFrame(
        {
            "id_comment": ["c1", "c1", "c2"],
            "sentiment_label": ["negative", "negative", "positive"],
            "timestamp": ["2026-08-01T10:00:00.000Z"] * 2 + ["2026-08-01T11:00:00.000Z"],
            "_run_id": ["r1", "r2", "r1"],
        }
    )

    resultado = aggregate_pct_negative_by_publication_day(df_history)

    assert len(resultado) == 1
    linha = resultado.iloc[0]
    assert linha["data"] == pd.Timestamp("2026-08-01").date()
    assert linha["pct_negativo"] == 0.5


def test_aggregate_pct_negative_by_publication_day_excludes_unparseable_timestamp():
    df_history = pd.DataFrame(
        {
            "id_comment": ["c1", "c2"],
            "sentiment_label": ["negative", "positive"],
            "timestamp": ["not-a-date", "2026-08-02T10:00:00.000Z"],
            "_run_id": ["r1", "r1"],
        }
    )

    resultado = aggregate_pct_negative_by_publication_day(df_history)

    assert len(resultado) == 1
    assert resultado.iloc[0]["data"] == pd.Timestamp("2026-08-02").date()


def test_aggregate_pct_negative_by_publication_day_returns_empty_df_when_column_missing():
    df_history = pd.DataFrame({"sentiment_label": ["negative"]})

    resultado = aggregate_pct_negative_by_publication_day(df_history)

    assert resultado.empty
    assert list(resultado.columns) == ["data", "pct_negativo"]


def test_aggregate_pct_negative_by_publication_day_returns_empty_df_when_history_is_empty():
    df_history = pd.DataFrame(
        columns=["id_comment", "sentiment_label", "timestamp", "_run_id"]
    )

    resultado = aggregate_pct_negative_by_publication_day(df_history)

    assert resultado.empty


# ---------------------------------------------------------------------------
# parse_publication_dates (ADR 0023 -- reusada por
# aggregate_pct_negative_by_publication_day e por dashboard/screens/resumo.py,
# em vez de cada chamador reimplementar o mesmo parse de timestamp)
# ---------------------------------------------------------------------------


def test_parse_publication_dates_converte_timestamp_iso_para_date():
    df = pd.DataFrame({"timestamp": ["2026-08-01T10:00:00.000Z", "2026-08-02T11:00:00.000Z"]})
    datas = parse_publication_dates(df)
    assert datas.tolist() == [datetime.date(2026, 8, 1), datetime.date(2026, 8, 2)]


def test_parse_publication_dates_timestamp_invalido_vira_nat():
    df = pd.DataFrame({"timestamp": ["not-a-date"]})
    datas = parse_publication_dates(df)
    assert pd.isna(datas.iloc[0])


def test_parse_publication_dates_coluna_ausente_retorna_serie_vazia():
    datas = parse_publication_dates(pd.DataFrame({"outra_coluna": [1]}))
    assert datas.empty


# ---------------------------------------------------------------------------
# filter_by_date_range (ADR 0023 -- compartilhada entre a linha do tempo do
# Radar, já agregada por dia, e o destaque de sentimento do Resumo, que
# filtra linhas de comentário individuais antes de agregar por tópico)
# ---------------------------------------------------------------------------


def test_filter_by_date_range_restringe_ao_intervalo_informado():
    df = pd.DataFrame(
        {
            "data": [datetime.date(2026, 8, 1), datetime.date(2026, 8, 3), datetime.date(2026, 8, 20)],
            "valor": [1, 2, 3],
        }
    )
    resultado = filter_by_date_range(
        df, "data", datetime.date(2026, 8, 1), datetime.date(2026, 8, 3)
    )
    assert resultado["valor"].tolist() == [1, 2]


def test_filter_by_date_range_sem_limites_retorna_tudo():
    df = pd.DataFrame({"data": [datetime.date(2026, 8, 1)], "valor": [1]})
    resultado = filter_by_date_range(df, "data", None, None)
    assert len(resultado) == 1


def test_filter_by_date_range_com_dataframe_vazio():
    resultado = filter_by_date_range(pd.DataFrame(columns=["data", "valor"]), "data", None, None)
    assert resultado.empty


# ---------------------------------------------------------------------------
# normalize_date_input_range (ADR 0023 -- normaliza o valor de retorno de
# `st.date_input(..., value=(min, max))`, que o Streamlit devolve como
# tupla de 1 elemento enquanto a analista ainda não escolheu a segunda data)
# ---------------------------------------------------------------------------


def test_normalize_date_input_range_com_duas_datas():
    inicio, fim = normalize_date_input_range(
        (datetime.date(2026, 8, 1), datetime.date(2026, 8, 10))
    )
    assert inicio == datetime.date(2026, 8, 1)
    assert fim == datetime.date(2026, 8, 10)


def test_normalize_date_input_range_com_uma_data_so():
    inicio, fim = normalize_date_input_range((datetime.date(2026, 8, 1),))
    assert inicio == fim == datetime.date(2026, 8, 1)


# ---------------------------------------------------------------------------
# quebrar_em_segmentos (ADR 0023, extraída de radar.py pela ADR 0024 quando
# ganhou um segundo consumidor real -- os testes abaixo eram
# `test_quebrar_em_segmentos_*` em tests/test_dashboard_screens_radar.py)
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


def test_quebrar_em_segmentos_quebra_quando_gap_maior_que_limiar():
    segmentos = quebrar_em_segmentos(_df_timeline_publicacao(), gap_dias=7)
    # 1/ago -> 3/ago: gap de 2 dias, continua no mesmo segmento.
    # 3/ago -> 20/ago: gap de 17 dias, > 7 -> novo segmento.
    assert len(segmentos) == 2
    assert segmentos[0]["data"].tolist() == [datetime.date(2026, 8, 1), datetime.date(2026, 8, 3)]
    assert segmentos[1]["data"].tolist() == [datetime.date(2026, 8, 20)]


def test_quebrar_em_segmentos_nao_quebra_quando_gap_menor_ou_igual_ao_limiar():
    df = pd.DataFrame(
        {
            "data": [datetime.date(2026, 8, 1), datetime.date(2026, 8, 8)],
            "pct_negativo": [0.10, 0.20],
        }
    )
    segmentos = quebrar_em_segmentos(df, gap_dias=7)
    assert len(segmentos) == 1
    assert len(segmentos[0]) == 2


def test_quebrar_em_segmentos_com_dataframe_vazio():
    assert quebrar_em_segmentos(pd.DataFrame(columns=["data", "pct_negativo"])) == []


def test_quebrar_em_segmentos_indiferente_ao_nome_da_segunda_coluna():
    # ADR 0024: a nova seção de "O que produzir" agrega numa coluna `valor`,
    # não `pct_negativo" -- a função só olha pra `data`.
    df = pd.DataFrame(
        {
            "data": [datetime.date(2026, 8, 1), datetime.date(2026, 8, 20)],
            "valor": [10, 20],
        }
    )
    segmentos = quebrar_em_segmentos(df, gap_dias=7)
    assert len(segmentos) == 2


# ---------------------------------------------------------------------------
# aggregate_metric_by_publication_day (ADR 0024 -- generaliza
# aggregate_pct_negative_by_publication_day pra curtidas/comentários/
# visualizações (soma) e quantidade de publicações (contagem))
# ---------------------------------------------------------------------------


def _df_conteudo_por_dia():
    return pd.DataFrame(
        {
            "likesCount": [10, 20, 5],
            "data_hora": pd.to_datetime(
                ["2026-08-01 10:00", "2026-08-01 18:00", "2026-08-03 09:00"]
            ),
        }
    )


def test_aggregate_metric_by_publication_day_soma_por_dia():
    resultado = aggregate_metric_by_publication_day(
        _df_conteudo_por_dia(), metric_col="likesCount", agg="sum"
    )
    assert resultado["data"].tolist() == [datetime.date(2026, 8, 1), datetime.date(2026, 8, 3)]
    assert resultado["valor"].tolist() == [30, 5]


def test_aggregate_metric_by_publication_day_conta_linhas_por_dia():
    resultado = aggregate_metric_by_publication_day(
        _df_conteudo_por_dia(), metric_col=None, agg="count"
    )
    assert resultado["data"].tolist() == [datetime.date(2026, 8, 1), datetime.date(2026, 8, 3)]
    assert resultado["valor"].tolist() == [2, 1]


def test_aggregate_metric_by_publication_day_dataframe_vazio():
    resultado = aggregate_metric_by_publication_day(pd.DataFrame(), metric_col="likesCount")
    assert resultado.empty
    assert list(resultado.columns) == ["data", "valor"]


def test_aggregate_metric_by_publication_day_sem_coluna_metrica_retorna_vazio():
    df = pd.DataFrame({"data_hora": pd.to_datetime(["2026-08-01"])})
    resultado = aggregate_metric_by_publication_day(df, metric_col="likesCount", agg="sum")
    assert resultado.empty


def test_aggregate_metric_by_publication_day_ignora_data_nao_parseavel():
    df = pd.DataFrame({"likesCount": [10, 20], "data_hora": ["2026-08-01", "nao-e-data"]})
    resultado = aggregate_metric_by_publication_day(df, metric_col="likesCount", agg="sum")
    assert resultado["data"].tolist() == [datetime.date(2026, 8, 1)]
    assert resultado["valor"].tolist() == [10]
