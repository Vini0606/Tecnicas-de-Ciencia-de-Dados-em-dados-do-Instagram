import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_top_n_bar(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str,
    top_n: int = 5,
) -> go.Figure:
    """Gráfico de barras horizontal com top N valores."""
    df_sorted = df.sort_values(by=x, ascending=True).tail(top_n)
    return px.bar(df_sorted, y=y, x=x, orientation="h", title=title, text_auto=True)


def plot_dual_axis(
    df: pd.DataFrame,
    bar_col: str,
    line_col: str,
    label_col: str,
    bar_name: str,
    line_name: str,
    title: str,
) -> go.Figure:
    """Gráfico de barras + linha com eixo Y duplo."""
    df_sorted = df.sort_values(by=bar_col, ascending=False)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=df_sorted[label_col], y=df_sorted[bar_col], name=bar_name),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=df_sorted[label_col],
            y=df_sorted[line_col],
            name=line_name,
            mode="lines+markers",
            line={"color": "red", "width": 3},
        ),
        secondary_y=True,
    )
    fig.update_layout(title_text=title, xaxis_title="Perfis")
    fig.update_yaxes(title_text=f"<b>{bar_name}</b>", secondary_y=False)
    fig.update_yaxes(title_text=f"<b>{line_name}</b>", secondary_y=True)
    return fig


def plot_correlation_heatmap(df: pd.DataFrame, method: str = "pearson") -> go.Figure:
    """Heatmap de correlação entre variáveis numéricas."""
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    corr = df[numeric_cols].corr(method=method)
    return px.imshow(
        corr, text_auto=True, aspect="auto", color_continuous_scale="RdBu_r", height=800
    )


def plot_value_counts(df: pd.DataFrame, column: str, title: str) -> go.Figure:
    """Gráfico de pizza com a contagem de valores de uma coluna categórica."""
    counts = df[column].value_counts().reset_index(name="count")
    counts.columns = [column, "count"]
    return px.pie(counts, names=column, values="count", title=title)


def plot_scatter(
    df: pd.DataFrame, x: str, y: str, height: int = 800, width: int | None = None
) -> go.Figure:
    """Gráfico de dispersão interativo."""
    return px.scatter(df, x=x, y=y, hover_data=df.columns, height=height, width=width)


def plot_engagement_trend(
    df_history: pd.DataFrame,
    y_col: str,
    label_col: str = "username",
    title: str | None = None,
) -> go.Figure:
    """Tendência de `y_col` ao longo de `_generated_at`, uma linha por `label_col`."""
    if df_history.empty:
        return go.Figure()
    return px.line(
        df_history.sort_values("_generated_at"),
        x="_generated_at",
        y=y_col,
        color=label_col,
        title=title,
        markers=True,
    )


def plot_sentiment_trend(df_sentiment_history: pd.DataFrame, title: str | None = None) -> go.Figure:
    """% de comentários com `sentiment_label == "positive"` por execução de
    modelagem (`_run_id`), ao longo de `_generated_at`. Espera
    `df_sentiment_history` já filtrado para um único governador (issue #61 --
    tendência de sentimento é narrativa por governador, não comparação entre
    pares, então uma única linha, sem `color=`, diferente de
    `plot_engagement_trend`)."""
    if df_sentiment_history.empty:
        return go.Figure()

    agrupado = (
        df_sentiment_history.assign(_positivo=df_sentiment_history["sentiment_label"] == "positive")
        .groupby(["_run_id", "_generated_at"])["_positivo"]
        .mean()
        .mul(100)
        .reset_index(name="% Positivo")
        .sort_values("_generated_at")
    )
    return px.line(
        agrupado,
        x="_generated_at",
        y="% Positivo",
        title=title,
        markers=True,
    )
