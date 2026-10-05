"""
Score ICE por PAUTA (issue #190, spec #182): `content_topic_priority_score`.

Pauta = assunto do conteudo (topico de discurso da LEGENDA do reel, ver
CONTEXT.md). Diferente de `TopicPriorityScorer` (que agrupa comentarios pelo
topico do proprio comentario), aqui os comentarios sao agrupados pela pauta do
reel em que foram feitos: comentario -> `id_reel` -> pauta.

Formula (ADR 0020, mesma do ICE de comentarios): Score = Impacto x Confianca x
Facilidade, com Impacto = alcance_normalizado x proporcao de positivos;
Confianca = media de `sentiment_score`; Facilidade fixa em 1.0 (v1). O alcance
da pauta e um proxy por engajamento (soma de curtidas + respostas dos
comentarios), normalizado por `x / (x + 1)` -- estavel entre execucoes.
Nunca chamar de "visualizacoes".

Regras de entrada: so a fonte `legenda` define pauta (transcricao exige plano
pago do coletor); o topico de ruido (-1) nao e pauta; `governor_discourse_topics`
tem reels duplicados, entao deduplica por `id_reel` antes de pontuar; cada reel
fica em uma unica pauta; comentarios de reels sem pauta sao ignorados.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.delta_io import write_delta
from src.modeling.gemini_refiner import DEGENERATE_TOPIC_LABEL
from src.schemas_delta import GOLD_CONTENT_TOPIC_PRIORITY_SCORE_SCHEMA

_RESULT_COLUMNS = [
    "Topic",
    "Name",
    "n_reels",
    "n_comentarios",
    "n_comentarios_positivos",
    "n_comentarios_negativos",
    "proporcao_sentimento_positivo",
    "alcance_pauta",
    "alcance_normalizado",
    "confianca",
    "impacto",
    "facilidade",
    "score",
]

_ID_PREFIX_RE = re.compile(r"^-?\d+_")


def clean_pauta_label(name: object, topic: object = None) -> str:
    """Normaliza o `Name` de um topico de discurso para um rotulo de pauta.

    Tira o prefixo `<id>_` do BERTopic. Rotulo refinado pelo Gemini chega como
    `<id>_<rotulo>_<kw1>_<kw2>...` (o rotulo tem espacos, as keywords nao):
    mantem so o rotulo. Nome bruto (`<id>_kw1_kw2...`) vira as keywords
    separadas por virgula. Sem palavra alguma (ex.: `1____`) ou nulo vira
    `DEGENERATE_TOPIC_LABEL`; o rotulo degenerado ja vem sem prefixo."""
    if name is None or pd.isna(name):
        return DEGENERATE_TOPIC_LABEL
    text = _ID_PREFIX_RE.sub("", str(name).strip(), count=1)
    parts = [p.strip() for p in text.split("_") if p.strip()]
    if not parts:
        return DEGENERATE_TOPIC_LABEL
    if " " in parts[0]:
        return parts[0]
    return ", ".join(parts)


class ContentTopicPriorityScorer:
    # Facilidade v1 fixa em 1.0 -- mesma justificativa da ADR 0020 /
    # `TopicPriorityScorer.FACILIDADE_V1` (sem dado de custo de producao).
    FACILIDADE_V1 = 1.0

    def score(self, df_sentiment: pd.DataFrame, df_discourse: pd.DataFrame) -> pd.DataFrame:
        """Score ICE por pauta. `df_sentiment` = `governor_sentiment` (so linhas
        `fonte="comentario"` contam); `df_discourse` = `governor_discourse_topics`.
        Uma linha por pauta, ordenada por `score` desc (desempate por `Topic`)."""
        missing = {"id_reel", "sentiment_label", "sentiment_score"} - set(df_sentiment.columns)
        if missing:
            raise ValueError(f"df_sentiment nao tem as colunas esperadas: {sorted(missing)}")
        missing = {"id_reel", "Topic", "Name"} - set(df_discourse.columns)
        if missing:
            raise ValueError(f"df_discourse nao tem as colunas esperadas: {sorted(missing)}")

        pautas = df_discourse
        if "fonte" in pautas.columns:
            pautas = pautas[pautas["fonte"] == "legenda"]
        pautas = pautas.dropna(subset=["id_reel", "Topic"])
        pautas = pautas[pautas["Topic"] != -1]
        # Reels duplicados (mesmo reel capturado mais de uma vez): uma pauta so.
        pautas = pautas.drop_duplicates(subset="id_reel", keep="first")
        pautas = pautas[["id_reel", "Topic", "Name"]]

        df = df_sentiment
        if "fonte" in df.columns:
            df = df[df["fonte"] == "comentario"]
        df = df.dropna(subset=["id_reel"])
        # Inner join: comentario de reel sem pauta e ignorado. Sem colunas
        # homonimas (Topic/Name do comentario) para nao colidir com a pauta.
        df = df.drop(columns=[c for c in ("Topic", "Name") if c in df.columns])
        df = df.merge(pautas, on="id_reel", how="inner")

        if df.empty:
            return pd.DataFrame(columns=_RESULT_COLUMNS)

        for col in ("likesCount", "repliesCount"):
            if col not in df.columns:
                df[col] = 0
        alcance = pd.to_numeric(df["likesCount"], errors="coerce").fillna(0.0) + pd.to_numeric(
            df["repliesCount"], errors="coerce"
        ).fillna(0.0)
        label = df["sentiment_label"].astype(str).str.lower()
        df = df.assign(
            _alcance=alcance,
            _positivo=label == "positive",
            _negativo=label == "negative",
            _name=[clean_pauta_label(n, t) for n, t in zip(df["Name"], df["Topic"], strict=True)],
        )

        grouped = (
            df.groupby("Topic")
            .agg(
                Name=("_name", "first"),
                n_reels=("id_reel", "nunique"),
                n_comentarios=("_positivo", "size"),
                n_comentarios_positivos=("_positivo", "sum"),
                n_comentarios_negativos=("_negativo", "sum"),
                proporcao_sentimento_positivo=("_positivo", "mean"),
                alcance_pauta=("_alcance", "sum"),
                confianca=("sentiment_score", "mean"),
            )
            .reset_index()
        )
        for col in (
            "Topic",
            "n_reels",
            "n_comentarios",
            "n_comentarios_positivos",
            "n_comentarios_negativos",
            "alcance_pauta",
        ):
            grouped[col] = grouped[col].astype("int64")
        # score nulo em linhas isoladas e ignorado pela media; so uma pauta com
        # TODAS as linhas nulas cai em 0.0.
        grouped["confianca"] = pd.to_numeric(grouped["confianca"], errors="coerce").fillna(0.0)

        grouped["alcance_normalizado"] = grouped["alcance_pauta"] / (grouped["alcance_pauta"] + 1.0)
        grouped["impacto"] = grouped["alcance_normalizado"] * grouped["proporcao_sentimento_positivo"]
        grouped["facilidade"] = self.FACILIDADE_V1
        grouped["score"] = grouped["impacto"] * grouped["confianca"] * grouped["facilidade"]

        return (
            grouped[_RESULT_COLUMNS]
            .sort_values(["score", "Topic"], ascending=[False, True])
            .reset_index(drop=True)
        )

    def write(
        self,
        df_scored: pd.DataFrame,
        path: Path | str,
        run_id: str,
        mode: str = "overwrite",
        generated_at: datetime | None = None,
    ) -> None:
        """Grava `content_topic_priority_score` (uma linha por pauta)."""
        df = df_scored.copy()
        df["_run_id"] = run_id
        df["_generated_at"] = generated_at or datetime.now(timezone.utc)
        write_delta(path, df, GOLD_CONTENT_TOPIC_PRIORITY_SCORE_SCHEMA, mode=mode)
