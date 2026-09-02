import pandas as pd
import plotly.graph_objects as go

from src.visualization.charts import plot_engagement_trend, plot_sentiment_trend


def _df_history():
    return pd.DataFrame(
        {
            "username": ["gov_a", "gov_a", "gov_b"],
            "TOTAL ENGAJAMENTO": [10, 20, 5],
            "_generated_at": pd.to_datetime(
                ["2026-05-01", "2026-05-02", "2026-05-01"], utc=True
            ),
        }
    )


def test_plot_engagement_trend_returns_figure():
    fig = plot_engagement_trend(_df_history(), y_col="TOTAL ENGAJAMENTO")
    assert isinstance(fig, go.Figure)


def test_plot_engagement_trend_uma_trace_por_governador():
    fig = plot_engagement_trend(_df_history(), y_col="TOTAL ENGAJAMENTO")
    trace_names = {trace.name for trace in fig.data}
    assert trace_names == {"gov_a", "gov_b"}


def test_plot_engagement_trend_nao_levanta_com_dataframe_vazio():
    df_vazio = pd.DataFrame(columns=["username", "TOTAL ENGAJAMENTO", "_generated_at"])
    fig = plot_engagement_trend(df_vazio, y_col="TOTAL ENGAJAMENTO")
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


def _df_sentiment_history():
    # Duas execuções (_run_id): r1 tem 1/2 positivo (50%), r2 tem 2/2 positivo
    # (100%) -- confirma que o cálculo de % Positivo agrupa por execução, não
    # mistura tudo numa média só.
    return pd.DataFrame(
        {
            "sentiment_label": ["positive", "negative", "positive", "positive"],
            "_run_id": ["r1", "r1", "r2", "r2"],
            "_generated_at": pd.to_datetime(
                ["2026-05-01", "2026-05-01", "2026-05-08", "2026-05-08"], utc=True
            ),
        }
    )


def test_plot_sentiment_trend_returns_figure():
    fig = plot_sentiment_trend(_df_sentiment_history())
    assert isinstance(fig, go.Figure)


def test_plot_sentiment_trend_calcula_percentual_positivo_por_execucao():
    fig = plot_sentiment_trend(_df_sentiment_history())
    valores = list(fig.data[0].y)
    assert valores == [50.0, 100.0]


def test_plot_sentiment_trend_nao_levanta_com_dataframe_vazio():
    df_vazio = pd.DataFrame(columns=["sentiment_label", "_run_id", "_generated_at"])
    fig = plot_sentiment_trend(df_vazio)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0
