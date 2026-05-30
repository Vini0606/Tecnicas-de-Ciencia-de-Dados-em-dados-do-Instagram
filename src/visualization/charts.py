import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_top5_bar(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str,
) -> go.Figure:
    """Gráfico de barras horizontal com top 5. Reutilizável em notebooks e dashboards."""
    df_sorted = df.sort_values(by=x, ascending=True).tail(5)
    return px.bar(df_sorted, y=y, x=x, orientation="h", title=title, text_auto=True)


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
            line=dict(color="red", width=3),
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


def plot_scatter(df: pd.DataFrame, x: str, y: str) -> go.Figure:
    """Gráfico de dispersão interativo."""
    return px.scatter(df, x=x, y=y, hover_data=df.columns, height=800)
