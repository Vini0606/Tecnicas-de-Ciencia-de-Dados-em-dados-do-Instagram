import pandas as pd

from dashboard.core.deltas import run_dates, week_over_week


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
