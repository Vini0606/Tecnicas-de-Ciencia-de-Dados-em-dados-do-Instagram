"""Comparação "este governador vs. seus pares" (issue #59 / ADR 0017).

Separado de `src/dashboard/filters.py` -- aquele módulo é sobre filtrar/
selecionar linhas, este é sobre derivar estatística de comparação a partir
de linhas já selecionadas. Função pura, sem I/O nem dependência de
Streamlit, mesmo padrão testável de `loaders.py`/`charts.py`.
"""

from __future__ import annotations

import pandas as pd

from src.dashboard.filters import select_governor_rows

_COLUMNS = ["metric", "value", "peer_mean", "delta", "rank", "total"]


def compute_governor_comparison(
    df_engagement: pd.DataFrame, governor_url: str, metrics: list[str]
) -> pd.DataFrame:
    """Para cada métrica em `metrics`, calcula o valor do governador, a média
    dos demais (peer_mean, excluindo o próprio governador), o delta entre os
    dois, e a posição no ranking (`rank`, maior valor = 1) entre os `total`
    governadores com valor não-nulo nessa métrica.

    Direção do ranking é uniforme (maior = melhor/rank 1) para todas as
    métricas -- `RECENCIA` já vem invertida (`1/(dias_desde_ultimo+1)`) do
    `EngagementAggregator`, então nenhuma métrica precisa de tratamento
    especial de direção.

    Retorna um DataFrame vazio (mesmas colunas) se `df_engagement` estiver
    vazio ou `governor_url` não tiver linha correspondente -- nunca levanta
    exceção, para o chamador degradar graciosamente (ver `pages/03_performance.py`)."""
    if df_engagement.empty:
        return pd.DataFrame(columns=_COLUMNS)

    universo_urls = df_engagement["inputUrl"].dropna().unique().tolist()
    linha_governador = select_governor_rows(df_engagement, governor_url, universo_urls)
    if linha_governador.empty:
        return pd.DataFrame(columns=_COLUMNS)

    indice_governador = linha_governador.index

    rows = []
    for metric in metrics:
        valores = pd.to_numeric(df_engagement[metric], errors="coerce").dropna()
        valor_governador = pd.to_numeric(linha_governador[metric], errors="coerce").iloc[0]

        outros = valores.drop(indice_governador, errors="ignore")
        peer_mean = outros.mean() if len(outros) else float("nan")

        rows.append(
            {
                "metric": metric,
                "value": valor_governador,
                "peer_mean": peer_mean,
                "delta": valor_governador - peer_mean,
                "rank": int((valores > valor_governador).sum()) + 1,
                "total": len(valores),
            }
        )

    return pd.DataFrame(rows, columns=_COLUMNS)


INEXPRESSIVO = "Inexpressivo"
GIGANTE_ADORMECIDO = "Gigante Adormecido"
NICHO = "Nicho"
SUPERSTAR = "Superstar"

_QUADRANT_COLUMNS = [
    "inputUrl",
    "followersCount",
    "% ENGAJAMENTO",
    "quadrante",
    "mediana_followers",
    "mediana_engajamento",
]


def compute_engagement_quadrants(df_engagement: pd.DataFrame) -> pd.DataFrame:
    """Classifica cada governador em um dos 4 quadrantes da matriz
    audiência × engajamento da VHL (ADR 0018): corte pela mediana de
    `followersCount` e de `% ENGAJAMENTO` sobre o `df_engagement` recebido.

    - baixa audiência + baixo engajamento -> Inexpressivo
    - alta audiência + baixo engajamento -> Gigante Adormecido
    - baixa audiência + alto engajamento -> Nicho
    - alta audiência + alto engajamento -> Superstar

    "Alta"/"alto" é estritamente acima da mediana -- o próprio ponto que
    define a mediana cai do lado "baixo" nos dois eixos, não fica "acima de
    si mesmo". Retorna DataFrame vazio (mesmas colunas) se `df_engagement`
    não tiver pelo menos 2 linhas com `followersCount`/`% ENGAJAMENTO`
    válidos -- mediana sem sentido com 1 ponto ou menos -- mesmo padrão de
    degradação graciosa de `compute_governor_comparison`. Também retorna
    vazio se `df_engagement` não tiver `followersCount`/`% ENGAJAMENTO`
    (chamadores como `check_engagement_quadrant`, em `recommendations.py`,
    recebem o mesmo `df_engagement` que outras regras usam com um
    subconjunto de colunas diferente -- sem esse guard, a ausência de
    qualquer uma das duas levantaria `KeyError` em vez de degradar)."""
    if df_engagement.empty or not {"followersCount", "% ENGAJAMENTO"} <= set(
        df_engagement.columns
    ):
        return pd.DataFrame(columns=_QUADRANT_COLUMNS)

    followers = pd.to_numeric(df_engagement["followersCount"], errors="coerce")
    engajamento = pd.to_numeric(df_engagement["% ENGAJAMENTO"], errors="coerce")
    validos = followers.notna() & engajamento.notna()
    if validos.sum() < 2:
        return pd.DataFrame(columns=_QUADRANT_COLUMNS)

    mediana_followers = followers[validos].median()
    mediana_engajamento = engajamento[validos].median()

    out = pd.DataFrame(
        {
            "inputUrl": df_engagement.loc[validos, "inputUrl"].values,
            "followersCount": followers[validos].values,
            "% ENGAJAMENTO": engajamento[validos].values,
        }
    )

    audiencia_alta = out["followersCount"] > mediana_followers
    engajamento_alto = out["% ENGAJAMENTO"] > mediana_engajamento

    out["quadrante"] = INEXPRESSIVO
    out.loc[audiencia_alta & ~engajamento_alto, "quadrante"] = GIGANTE_ADORMECIDO
    out.loc[~audiencia_alta & engajamento_alto, "quadrante"] = NICHO
    out.loc[audiencia_alta & engajamento_alto, "quadrante"] = SUPERSTAR

    out["mediana_followers"] = mediana_followers
    out["mediana_engajamento"] = mediana_engajamento

    return out
