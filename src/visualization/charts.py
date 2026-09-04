import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Paleta de fallback da skill /dataviz (references/palette.md) -- usada sempre
# que a tentativa de puxar hex da identidade visual da IESB reprova o
# validador (scripts/validate_palette.js). Ver issues #67/#68: o par
# diverging vermelho/azul da IESB reprova banda de luminosidade + contraste
# no modo escuro, e o par categórico dourado/verde reprova separação sob
# daltonismo (ΔE 1.0 sob protanopia) nos dois modos -- por isso os dois
# gráficos abaixo caem pro par genérico documentado, não pras cores da marca.
_DIVERGING_NEGATIVE_COLOR = "#e34948"
_DIVERGING_POSITIVE_COLOR = "#2a78d6"
_DIVERGING_NEUTRAL_COLOR = "#f0efec"
_CATEGORICAL_SLOT_1 = "#2a78d6"
_CATEGORICAL_SLOT_2 = "#eb6834"
_MUTED_CONTEXT_COLOR = "#898781"

# Abaixo desse percentual, o rótulo "XX%" não cabe com respiro dentro do
# segmento (issue #67: "medir antes de renderizar... nunca usar overflow:
# hidden pra cortar"). Plotly não expõe medição de texto pré-render, então
# isso é um proxy pragmático -- segmento menor que isso conta só com
# legenda/tooltip, não rótulo direto.
_MIN_SEGMENT_PCT_FOR_LABEL = 6.0


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


def plot_sentiment_diverging_bar(
    df: pd.DataFrame, column: str = "sentiment_label", title: str | None = None
) -> go.Figure:
    """Distribuição de sentimento (negativo/neutro/positivo) como uma diverging
    stacked bar centrada no zero -- sentimento é uma escala ordenada (Likert),
    não categorias nominais soltas, então o segmento neutro fica metade à
    esquerda e metade à direita do zero, negativo cresce pra esquerda a partir
    daí e positivo pra direita (issue #67). Substitui a pizza de
    `plot_value_counts` (removida -- essa era a única chamadora)."""
    serie = df[column].dropna()
    if serie.empty:
        return go.Figure()

    neg_pct = (serie == "negative").mean() * 100
    neu_pct = (serie == "neutral").mean() * 100
    pos_pct = (serie == "positive").mean() * 100

    segmentos = [
        ("Negativo", -(neg_pct + neu_pct / 2), neg_pct, _DIVERGING_NEGATIVE_COLOR, "white"),
        ("Neutro", -neu_pct / 2, neu_pct, _DIVERGING_NEUTRAL_COLOR, "#52514e"),
        ("Positivo", neu_pct / 2, pos_pct, _DIVERGING_POSITIVE_COLOR, "white"),
    ]

    fig = go.Figure()
    for nome, base, valor, cor, cor_texto in segmentos:
        fig.add_trace(
            go.Bar(
                y=["Sentimento"],
                x=[valor],
                base=[base],
                orientation="h",
                name=nome,
                marker_color=cor,
                text=f"{valor:.0f}%" if valor >= _MIN_SEGMENT_PCT_FOR_LABEL else None,
                textposition="auto",
                textfont={"color": cor_texto},
            )
        )
    fig.update_layout(barmode="overlay", title=title, showlegend=True)
    fig.update_xaxes(showticklabels=False, zeroline=False, showgrid=False)
    fig.update_yaxes(showticklabels=False)
    return fig


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


def plot_engagement_group_summary_trend(
    df_history: pd.DataFrame, y_col: str, title: str | None = None
) -> go.Figure:
    """Média e mediana de `y_col` por execução (`_run_id`/`_generated_at`)
    entre todos os governadores de `df_history` -- usada no lugar de 1 linha
    por governador (`plot_engagement_trend`) quando "Todos os Governadores"
    está selecionado em Performance: até 27 séries/cores no mesmo gráfico
    estoura o teto categórico da paleta e fica ilegível (issue #68)."""
    if df_history.empty:
        return go.Figure()

    agrupado = (
        df_history.groupby(["_run_id", "_generated_at"])[y_col]
        .agg(["mean", "median"])
        .reset_index()
        .sort_values("_generated_at")
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=agrupado["_generated_at"],
            y=agrupado["mean"],
            name="Média",
            mode="lines+markers",
            line={"color": _CATEGORICAL_SLOT_1},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=agrupado["_generated_at"],
            y=agrupado["median"],
            name="Mediana",
            mode="lines+markers",
            line={"color": _CATEGORICAL_SLOT_2},
        )
    )
    fig.update_layout(title=title)
    return fig


def plot_engagement_trend_with_group_context(
    df_governador: pd.DataFrame,
    df_grupo: pd.DataFrame,
    y_col: str,
    governor_label: str,
    title: str | None = None,
) -> go.Figure:
    """Linha do governador selecionado em destaque + média de `y_col` do grupo
    inteiro (`df_grupo`, não filtrado por governador) como linha de contexto
    cinza atrás dela -- padrão "emphasis" da `/dataviz`: 1 série é o ponto, o
    resto é contexto. Dá à tendência ao longo do tempo a mesma leitura "vs.
    pares" que os cards de comparação já dão em texto (issue #68)."""
    df_governador_ordenado = df_governador.sort_values("_generated_at")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df_governador_ordenado["_generated_at"],
            y=df_governador_ordenado[y_col],
            name=governor_label,
            mode="lines+markers",
            line={"color": _CATEGORICAL_SLOT_1},
        )
    )

    if not df_grupo.empty:
        media_grupo = (
            df_grupo.groupby(["_run_id", "_generated_at"])[y_col]
            .mean()
            .reset_index(name=y_col)
            .sort_values("_generated_at")
        )
        fig.add_trace(
            go.Scatter(
                x=media_grupo["_generated_at"],
                y=media_grupo[y_col],
                name="Média do grupo",
                mode="lines",
                line={"color": _MUTED_CONTEXT_COLOR},
            )
        )

    fig.update_layout(title=title)
    return fig


def plot_engagement_quadrant_matrix(
    df_quadrantes: pd.DataFrame,
    governor_url: str | None = None,
    governor_label: str | None = None,
    title: str | None = None,
) -> go.Figure:
    """Matriz de quadrantes (ADR 0018): `followersCount` × `% ENGAJAMENTO`,
    com linhas de corte na mediana de cada eixo e um rótulo por quadrante nos
    4 cantos. Espera `df_quadrantes` no formato de saída de
    `compute_engagement_quadrants` (colunas `inputUrl`, `followersCount`,
    `% ENGAJAMENTO`, `quadrante`, `mediana_followers`, `mediana_engajamento`).

    Identidade de quadrante não é carregada por cor nos pontos -- a paleta
    categórica de fallback deste projeto (skill /dataviz, issues #67/#68) só
    valida "all-pairs" (necessário em scatter, onde qualquer par de pontos
    pode ficar lado a lado) para os 3 primeiros slots; o 4º já falha contra o
    3º. O quadrante é uma região geométrica definida pelas linhas de
    mediana + rótulo de canto, não uma cor de série; pontos usam só destaque
    (`governor_url`) vs. contexto, mesmo padrão "emphasis" de
    `plot_engagement_trend_with_group_context`.

    `governor_url` opcional -- `None` (ex.: "Todos os Governadores"
    selecionado) deixa todos os pontos no mesmo nível de contexto, sem
    destaque."""
    if df_quadrantes.empty:
        return go.Figure()

    mediana_followers = df_quadrantes["mediana_followers"].iloc[0]
    mediana_engajamento = df_quadrantes["mediana_engajamento"].iloc[0]

    destaque = (
        df_quadrantes["inputUrl"] == governor_url
        if governor_url is not None
        else pd.Series(False, index=df_quadrantes.index)
    )

    hovertemplate = (
        "Seguidores: %{x:,.0f}<br>% Engajamento: %{y:.4f}"
        "<br>Quadrante: %{customdata}<extra></extra>"
    )

    fig = go.Figure()

    contexto = df_quadrantes.loc[~destaque]
    fig.add_trace(
        go.Scatter(
            x=contexto["followersCount"],
            y=contexto["% ENGAJAMENTO"],
            mode="markers",
            name="Demais governadores" if destaque.any() else "Governadores",
            marker={"color": _MUTED_CONTEXT_COLOR, "size": 9},
            customdata=contexto["quadrante"],
            hovertemplate=hovertemplate,
        )
    )

    if destaque.any():
        selecionado = df_quadrantes.loc[destaque]
        fig.add_trace(
            go.Scatter(
                x=selecionado["followersCount"],
                y=selecionado["% ENGAJAMENTO"],
                mode="markers",
                name=governor_label or "Selecionado",
                marker={
                    "color": _CATEGORICAL_SLOT_1,
                    "size": 14,
                    "line": {"color": "white", "width": 1},
                },
                customdata=selecionado["quadrante"],
                hovertemplate=hovertemplate,
            )
        )

    fig.add_vline(x=mediana_followers, line_dash="dash", line_color=_MUTED_CONTEXT_COLOR)
    fig.add_hline(y=mediana_engajamento, line_dash="dash", line_color=_MUTED_CONTEXT_COLOR)

    for texto, x_paper, y_paper in [
        ("Nicho", 0.02, 0.98),
        ("Superstar", 0.98, 0.98),
        ("Inexpressivo", 0.02, 0.02),
        ("Gigante Adormecido", 0.98, 0.02),
    ]:
        fig.add_annotation(
            x=x_paper,
            y=y_paper,
            xref="paper",
            yref="paper",
            text=texto,
            showarrow=False,
            font={"color": _MUTED_CONTEXT_COLOR, "size": 11},
        )

    fig.update_layout(
        title=title,
        xaxis_title="Seguidores",
        yaxis_title="% Engajamento",
    )
    return fig
