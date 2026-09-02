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
