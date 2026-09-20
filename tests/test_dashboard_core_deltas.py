import pandas as pd

from dashboard.core.deltas import (
    aggregate_pct_negative_by_publication_day,
    deduplicate_by_first_seen,
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
