"""Motor de regras determinístico da página Recommendations (issue #65 / ADR
0017). Cada `check_*` é uma função pura: recebe DataFrame(s) já carregados +
o `inputUrl` do governador selecionado, e retorna uma mensagem em português
já com os números reais preenchidos (`str`) se a regra disparou, ou `None`
caso contrário -- nunca levanta exceção por dado insuficiente, só não
dispara (ver docstring de cada função para o que conta como "insuficiente").

Mensagens são templates Python, não texto gerado por LLM -- a ADR 0017
decidiu redação via LLM como refinamento futuro, fora do escopo desta spec.
"""

from __future__ import annotations

import pandas as pd

from src.dashboard.filters import select_governor_rows


def _peer_urls(df_profile_clusters: pd.DataFrame, governor_url: str) -> list[str] | None:
    """inputUrl dos pares de cluster de perfil do governador (mesmo
    `cluster_perfil_engajamento`, excluindo o próprio). `None` se o
    governador não tiver cluster atribuído ou não tiver nenhum par."""
    if df_profile_clusters.empty or "inputUrl" not in df_profile_clusters.columns:
        return None
    universo = df_profile_clusters["inputUrl"].dropna().unique().tolist()
    linha_governador = select_governor_rows(df_profile_clusters, governor_url, universo)
    if linha_governador.empty:
        return None
    cluster_governador = linha_governador["cluster_perfil_engajamento"].iloc[0]
    if pd.isna(cluster_governador):
        return None

    mesmo_cluster = df_profile_clusters[
        df_profile_clusters["cluster_perfil_engajamento"] == cluster_governador
    ]
    # Exclui o próprio governador por índice -- mesmo idioma de
    # `comparisons.py::compute_governor_comparison` (`.drop(..., errors="ignore")`)
    # pro mesmo conceito ("tira a própria linha da comparação com pares").
    pares = mesmo_cluster.drop(linha_governador.index, errors="ignore")
    urls = pares["inputUrl"].dropna().unique().tolist()
    return urls or None


def _pct_diff_vs_peers(valor_proprio: float, valores_pares: pd.Series) -> float | None:
    """% de diferença entre `valor_proprio` e a média de `valores_pares`
    (positivo = próprio maior que a média dos pares). `None` se não houver
    pares com valor válido, ou se a média dos pares for <= 0 (divisão sem
    sentido)."""
    valores_pares = valores_pares.dropna()
    if valores_pares.empty:
        return None
    media_pares = valores_pares.mean()
    if media_pares <= 0:
        return None
    return (valor_proprio - media_pares) / media_pares * 100


def check_engagement_drop(
    df_engagement_history: pd.DataFrame,
    governor_url: str,
    min_execucoes: int = 2,
    limiar_pct: float = 15.0,
) -> str | None:
    """Dispara se `% ENGAJAMENTO` da última execução caiu `limiar_pct`% ou
    mais (relativo) vs. a média das execuções anteriores do mesmo
    governador. Precisa de pelo menos `min_execucoes` execuções -- menos
    que isso, retorna `None` (não há "anterior" pra comparar)."""
    if df_engagement_history.empty:
        return None
    universo = df_engagement_history["inputUrl"].dropna().unique().tolist()
    df_governador = select_governor_rows(df_engagement_history, governor_url, universo)
    if len(df_governador) < min_execucoes:
        return None

    df_ordenado = df_governador.sort_values("_generated_at")
    anteriores = df_ordenado["% ENGAJAMENTO"].iloc[:-1]
    ultima = df_ordenado["% ENGAJAMENTO"].iloc[-1]
    media_anterior = anteriores.mean()
    if media_anterior <= 0:
        return None

    queda_pct = (media_anterior - ultima) / media_anterior * 100
    if queda_pct >= limiar_pct:
        return (
            f"Seu engajamento caiu {queda_pct:.1f}% na última execução "
            f"em relação à média das execuções anteriores."
        )
    return None


def check_sentiment_trend_drop(
    df_sentiment_history: pd.DataFrame,
    governor_url: str,
    min_execucoes: int = 2,
    limiar_pp: float = 10.0,
) -> str | None:
    """Dispara se o `% Positivo` (mesmo cálculo de `plot_sentiment_trend`,
    Insights) da última execução caiu `limiar_pp` pontos percentuais ou mais
    vs. a média das execuções anteriores. Pontos percentuais, não % relativo
    -- mais estável perto de zero. Precisa de pelo menos `min_execucoes`
    execuções."""
    if df_sentiment_history.empty:
        return None
    universo = df_sentiment_history["inputUrl"].dropna().unique().tolist()
    df_governador = select_governor_rows(df_sentiment_history, governor_url, universo)
    if df_governador.empty:
        return None

    por_execucao = (
        df_governador.assign(_positivo=df_governador["sentiment_label"] == "positive")
        .groupby(["_run_id", "_generated_at"])["_positivo"]
        .mean()
        .mul(100)
        .reset_index(name="% Positivo")
        .sort_values("_generated_at")
    )
    if len(por_execucao) < min_execucoes:
        return None

    anteriores = por_execucao["% Positivo"].iloc[:-1]
    ultima = por_execucao["% Positivo"].iloc[-1]
    media_anterior = anteriores.mean()
    queda_pp = media_anterior - ultima
    if queda_pp >= limiar_pp:
        return (
            f"O sentimento sobre você caiu {queda_pp:.1f} pontos percentuais "
            f"de positividade na última execução em relação à média anterior."
        )
    return None


def check_negative_sentiment_topic(
    df_sentiment: pd.DataFrame,
    governor_url: str,
    min_comentarios: int = 5,
    limiar_pct: float = 50.0,
) -> str | None:
    """Dispara se algum tópico (`Name`) com pelo menos `min_comentarios`
    comentários do governador tiver `limiar_pct`% ou mais de comentários
    negativos. Tópicos com poucos comentários são ignorados (ruído -- um
    único comentário negativo não é "concentração")."""
    if df_sentiment.empty or "Name" not in df_sentiment.columns:
        return None
    universo = df_sentiment["inputUrl"].dropna().unique().tolist()
    df_governador = select_governor_rows(df_sentiment, governor_url, universo)
    if df_governador.empty:
        return None

    por_topico = (
        df_governador.dropna(subset=["Name"])
        .assign(_negativo=lambda d: d["sentiment_label"] == "negative")
        .groupby("Name")
        .agg(total=("_negativo", "size"), pct_negativo=("_negativo", "mean"))
    )
    por_topico["pct_negativo"] *= 100
    candidatos = por_topico[por_topico["total"] >= min_comentarios]
    if candidatos.empty:
        return None

    pior_topico = candidatos["pct_negativo"].idxmax()
    pior_pct = candidatos.loc[pior_topico, "pct_negativo"]
    if pior_pct >= limiar_pct:
        return (
            f'O tópico "{pior_topico}" concentra {pior_pct:.0f}% de comentários '
            f"negativos entre os assuntos mais discutidos."
        )
    return None


def check_shorter_or_longer_reels_than_peers(
    df_reels: pd.DataFrame,
    df_profile_clusters: pd.DataFrame,
    governor_url: str,
    limiar_pct: float = 20.0,
) -> str | None:
    """Dispara se a duração média dos reels do governador for
    `limiar_pct`% ou mais diferente (mais curta ou mais longa) da duração
    média dos reels dos pares do mesmo cluster de perfil por engajamento.
    Precisa de ao menos 1 par no mesmo cluster com dado de duração."""
    if df_reels.empty or "videoDuration" not in df_reels.columns:
        return None
    pares_urls = _peer_urls(df_profile_clusters, governor_url)
    if not pares_urls:
        return None

    universo = df_reels["inputUrl"].dropna().unique().tolist()
    reels_governador = select_governor_rows(df_reels, governor_url, universo)
    duracao_propria = pd.to_numeric(reels_governador["videoDuration"], errors="coerce").dropna()
    if duracao_propria.empty:
        return None

    duracao_pares = pd.to_numeric(
        df_reels.loc[df_reels["inputUrl"].isin(pares_urls), "videoDuration"], errors="coerce"
    )
    diff_pct = _pct_diff_vs_peers(duracao_propria.mean(), duracao_pares)
    if diff_pct is not None and abs(diff_pct) >= limiar_pct:
        direcao = "mais curtos" if diff_pct < 0 else "mais longos"
        return (
            f"Seus reels são {direcao} que os dos seus pares de cluster "
            f"({abs(diff_pct):.0f}% de diferença na duração média)."
        )
    return None


def check_frequency_below_cluster_peers(
    df_engagement: pd.DataFrame,
    df_profile_clusters: pd.DataFrame,
    governor_url: str,
    limiar_pct: float = 20.0,
) -> str | None:
    """Dispara se `FREQUENCIA` do governador estiver `limiar_pct`% ou mais
    abaixo da média dos pares do mesmo cluster de perfil por engajamento.
    Só olha "abaixo" (não "acima") -- postar mais que os pares não é, por
    si só, um alerta."""
    if df_engagement.empty or "FREQUENCIA" not in df_engagement.columns:
        return None
    pares_urls = _peer_urls(df_profile_clusters, governor_url)
    if not pares_urls:
        return None

    universo = df_engagement["inputUrl"].dropna().unique().tolist()
    linha_governador = select_governor_rows(df_engagement, governor_url, universo)
    if linha_governador.empty:
        return None
    freq_propria = pd.to_numeric(linha_governador["FREQUENCIA"], errors="coerce").iloc[0]
    if pd.isna(freq_propria):
        return None

    freq_pares = pd.to_numeric(
        df_engagement.loc[df_engagement["inputUrl"].isin(pares_urls), "FREQUENCIA"],
        errors="coerce",
    )
    # _pct_diff_vs_peers é "próprio vs. pares" (positivo = próprio maior) --
    # "abaixo dos pares" é o lado negativo dessa mesma convenção, por isso o
    # limiar aqui é <= -limiar_pct, não >= limiar_pct.
    diff_pct = _pct_diff_vs_peers(freq_propria, freq_pares)
    if diff_pct is not None and diff_pct <= -limiar_pct:
        return (
            f"Sua frequência de postagem está {abs(diff_pct):.0f}% abaixo da média "
            f"dos seus pares de cluster."
        )
    return None


def compute_recommendations(
    governor_url: str,
    df_engagement: pd.DataFrame,
    df_engagement_history: pd.DataFrame,
    df_sentiment: pd.DataFrame,
    df_sentiment_history: pd.DataFrame,
    df_reels: pd.DataFrame,
    df_profile_clusters: pd.DataFrame,
) -> list[str]:
    """Roda as 5 regras na ordem definida, retorna as mensagens disparadas
    (lista vazia se nenhuma regra disparou)."""
    checagens = [
        check_engagement_drop(df_engagement_history, governor_url),
        check_sentiment_trend_drop(df_sentiment_history, governor_url),
        check_negative_sentiment_topic(df_sentiment, governor_url),
        check_shorter_or_longer_reels_than_peers(df_reels, df_profile_clusters, governor_url),
        check_frequency_below_cluster_peers(df_engagement, df_profile_clusters, governor_url),
    ]
    return [mensagem for mensagem in checagens if mensagem is not None]
