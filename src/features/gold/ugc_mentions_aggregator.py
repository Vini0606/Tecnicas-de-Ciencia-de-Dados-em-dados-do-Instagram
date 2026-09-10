"""
Gold de UGC de criação (ADR 0020, Ficha 8 / issue #93): `governor_ugc_mentions`.

Ao contrário de `EngagementAggregator` (que agrega no ato de gravar a Gold),
aqui a tabela Gold em si guarda UMA LINHA POR POST DE UGC -- decisão
explícita da issue: a agregação por governador é uma view/query sobre essa
tabela, não a granularidade de armazenamento (mesmo raciocínio de
`GOLD_CLUSTERS_SCHEMA`/`GOLD_POST_PERFORMANCE_PREDICTIONS_SCHEMA`).
`GovernorUGCAggregator` faz as duas coisas: `enrich` grava a tabela de grão
fino (com `is_organic` derivado), `aggregate_by_governor` é a "view" -- uma
função pura sobre o resultado de `enrich`, não persistida em Delta.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.delta_io import write_delta
from src.schemas_delta import GOLD_UGC_MENTIONS_SCHEMA


class GovernorUGCAggregator:
    # Nomeado `enrich`, não `aggregate` (diferente de
    # `EngagementAggregator.aggregate`) DE PROPÓSITO: este método NÃO reduz
    # linhas -- grava a Gold no grão de 1-linha-por-post (issue #93). Quem
    # agrega de verdade é `aggregate_by_governor`, abaixo, que não escreve
    # Delta nenhum. Ver docstring do módulo.
    def enrich(self, df_silver: pd.DataFrame, run_id: str) -> pd.DataFrame:
        df = df_silver.copy()

        # Crítico (ADR 0020, Ficha 8): separa UGC orgânico de publi paga
        # ANTES de qualquer agregação -- contar publi como "apoio
        # espontâneo" infla falsamente o nível "Criar" do funil COBRA-RACE.
        for col in ("isPaidPartnership", "isAd", "isAffiliate"):
            if col not in df.columns:
                df[col] = False
        df["is_organic"] = ~(
            df["isPaidPartnership"].fillna(False).astype(bool)
            | df["isAd"].fillna(False).astype(bool)
            | df["isAffiliate"].fillna(False).astype(bool)
        )

        df = df.drop(
            columns=["isPaidPartnership", "isAd", "isAffiliate", "_ingested_at", "_source_layer"],
            errors="ignore",
        )
        df["_run_id"] = run_id
        df["_generated_at"] = datetime.now(timezone.utc)
        return df

    def write(self, df_gold: pd.DataFrame, path: Path | str, mode: str = "overwrite") -> None:
        write_delta(path, df_gold, GOLD_UGC_MENTIONS_SCHEMA, mode=mode)

    def aggregate_by_governor(self, df_gold: pd.DataFrame) -> pd.DataFrame:
        """Volume/engajamento de UGC por governador -- a "view" sobre
        `governor_ugc_mentions` que alimenta o estágio Engage/Criar do
        funil COBRA-RACE (`COUNT` de posts orgânicos + `SUM(likes+comments)`
        deles). Publi (`is_organic == False`) é filtrada ANTES de agregar,
        não depois -- ver teste comparando com/sem o filtro.

        Privacidade (ADR 0020, Ficha 8): o resultado é agregado por
        `governor_username` -- nunca expõe `authorUsername` individual, só
        contagens/médias, para não identificar cidadãos comuns em telas de
        agregado. Ver limitação declarada de viés de volume: governadores
        mais populares tendem a ter muito mais menções, e este método não
        normaliza por tamanho de audiência (fora de escopo desta issue)."""
        if df_gold.empty:
            return pd.DataFrame(
                columns=[
                    "governor_username",
                    "count_organic",
                    "count_paid",
                    "avg_engagement_organic",
                    "pct_organic",
                ]
            )

        organic = df_gold[df_gold["is_organic"]]
        engagement_organic = organic["likesCount"].fillna(0) + organic["commentsCount"].fillna(0)

        counts_total = df_gold.groupby("governor_username").size().rename("count_total")
        counts_organic = organic.groupby("governor_username").size().rename("count_organic")
        avg_engagement = (
            engagement_organic.groupby(organic["governor_username"])
            .mean()
            .rename("avg_engagement_organic")
        )

        result = pd.concat([counts_total, counts_organic, avg_engagement], axis=1).reset_index()
        result["count_organic"] = result["count_organic"].fillna(0).astype("int64")
        result["count_total"] = result["count_total"].fillna(0).astype("int64")
        result["count_paid"] = result["count_total"] - result["count_organic"]
        result["avg_engagement_organic"] = result["avg_engagement_organic"].fillna(0.0)
        result["pct_organic"] = (
            result["count_organic"] / result["count_total"].replace(0, pd.NA)
        ).fillna(0.0)

        return result[
            ["governor_username", "count_organic", "count_paid", "avg_engagement_organic", "pct_organic"]
        ]
