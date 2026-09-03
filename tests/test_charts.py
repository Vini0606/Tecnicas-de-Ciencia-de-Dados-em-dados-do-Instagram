import pandas as pd
import plotly.graph_objects as go
import pytest

from src.visualization.charts import (
    plot_engagement_group_summary_trend,
    plot_engagement_trend,
    plot_engagement_trend_with_group_context,
    plot_sentiment_diverging_bar,
    plot_sentiment_trend,
)


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


def _df_sentiment_counts():
    # 1 negativo, 1 neutro, 2 positivos -- 25%/25%/50%.
    return pd.DataFrame(
        {"sentiment_label": ["negative", "neutral", "positive", "positive"]}
    )


def test_plot_sentiment_diverging_bar_returns_figure_com_3_traces():
    fig = plot_sentiment_diverging_bar(_df_sentiment_counts())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 3


def test_plot_sentiment_diverging_bar_calcula_percentuais():
    fig = plot_sentiment_diverging_bar(_df_sentiment_counts())
    por_nome = {trace.name: trace.x[0] for trace in fig.data}
    assert por_nome["Negativo"] == 25.0
    assert por_nome["Neutro"] == 25.0
    assert por_nome["Positivo"] == 50.0


def test_plot_sentiment_diverging_bar_neutro_centralizado_no_zero():
    fig = plot_sentiment_diverging_bar(_df_sentiment_counts())
    trace_neutro = next(trace for trace in fig.data if trace.name == "Neutro")
    assert trace_neutro.base[0] + trace_neutro.x[0] / 2 == pytest.approx(0.0)


def test_plot_sentiment_diverging_bar_nao_levanta_com_dataframe_vazio():
    df_vazio = pd.DataFrame(columns=["sentiment_label"])
    fig = plot_sentiment_diverging_bar(df_vazio)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


def test_plot_sentiment_diverging_bar_categoria_ausente_nao_quebra():
    df_sem_negativo = pd.DataFrame({"sentiment_label": ["neutral", "positive"]})
    fig = plot_sentiment_diverging_bar(df_sem_negativo)
    trace_negativo = next(trace for trace in fig.data if trace.name == "Negativo")
    assert trace_negativo.x[0] == 0.0


def _df_history_multi_governador():
    return pd.DataFrame(
        {
            "inputUrl": ["a", "a", "b", "b"],
            "_run_id": ["r1", "r2", "r1", "r2"],
            "TOTAL ENGAJAMENTO": [10.0, 30.0, 20.0, 50.0],
            "_generated_at": pd.to_datetime(
                ["2026-05-01", "2026-05-08", "2026-05-01", "2026-05-08"], utc=True
            ),
        }
    )


def test_plot_engagement_group_summary_trend_returns_media_e_mediana():
    fig = plot_engagement_group_summary_trend(
        _df_history_multi_governador(), y_col="TOTAL ENGAJAMENTO"
    )
    trace_names = {trace.name for trace in fig.data}
    assert trace_names == {"Média", "Mediana"}


def test_plot_engagement_group_summary_trend_calcula_media_e_mediana_por_execucao():
    # r1: [10, 20] -> média 15, mediana 15. r2: [30, 50] -> média 40, mediana 40.
    fig = plot_engagement_group_summary_trend(
        _df_history_multi_governador(), y_col="TOTAL ENGAJAMENTO"
    )
    por_nome = {trace.name: list(trace.y) for trace in fig.data}
    assert por_nome["Média"] == [15.0, 40.0]
    assert por_nome["Mediana"] == [15.0, 40.0]


def test_plot_engagement_group_summary_trend_nao_levanta_com_dataframe_vazio():
    df_vazio = pd.DataFrame(
        columns=["inputUrl", "_run_id", "TOTAL ENGAJAMENTO", "_generated_at"]
    )
    fig = plot_engagement_group_summary_trend(df_vazio, y_col="TOTAL ENGAJAMENTO")
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


def _df_history_um_governador():
    return pd.DataFrame(
        {
            "inputUrl": ["a", "a"],
            "_run_id": ["r1", "r2"],
            "TOTAL ENGAJAMENTO": [10.0, 30.0],
            "_generated_at": pd.to_datetime(["2026-05-01", "2026-05-08"], utc=True),
        }
    )


def test_plot_engagement_trend_with_group_context_returns_governador_e_media_grupo():
    fig = plot_engagement_trend_with_group_context(
        df_governador=_df_history_um_governador(),
        df_grupo=_df_history_multi_governador(),
        y_col="TOTAL ENGAJAMENTO",
        governor_label="Fulano",
    )
    trace_names = {trace.name for trace in fig.data}
    assert trace_names == {"Fulano", "Média do grupo"}


def test_plot_engagement_trend_with_group_context_media_do_grupo_usa_df_grupo():
    # df_grupo (a e b) tem médias [15, 40] por execução -- não deve bater com o
    # valor do próprio df_governador ([10, 30]), confirmando que a média de
    # contexto vem do grupo inteiro, não do governador selecionado.
    fig = plot_engagement_trend_with_group_context(
        df_governador=_df_history_um_governador(),
        df_grupo=_df_history_multi_governador(),
        y_col="TOTAL ENGAJAMENTO",
        governor_label="Fulano",
    )
    trace_media = next(trace for trace in fig.data if trace.name == "Média do grupo")
    assert list(trace_media.y) == [15.0, 40.0]


def test_plot_engagement_trend_with_group_context_governador_vazio_nao_levanta():
    df_vazio = pd.DataFrame(
        columns=["inputUrl", "_run_id", "TOTAL ENGAJAMENTO", "_generated_at"]
    )
    fig = plot_engagement_trend_with_group_context(
        df_governador=df_vazio,
        df_grupo=_df_history_multi_governador(),
        y_col="TOTAL ENGAJAMENTO",
        governor_label="Fulano",
    )
    assert isinstance(fig, go.Figure)
    trace_names = {trace.name for trace in fig.data}
    assert trace_names == {"Fulano", "Média do grupo"}
