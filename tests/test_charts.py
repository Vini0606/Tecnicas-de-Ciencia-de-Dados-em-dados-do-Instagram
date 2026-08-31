import pandas as pd
import plotly.graph_objects as go

from src.visualization.charts import plot_engagement_trend


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
