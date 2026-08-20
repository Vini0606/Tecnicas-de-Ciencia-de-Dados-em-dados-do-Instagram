"""Análise de sentimento dos comentários"""

from __future__ import annotations

from typing import Callable

import pandas as pd
from transformers import pipeline

from src.modeling.config import SentimentConfig


def _build_pipeline(model_name: str) -> Callable:
    return pipeline("sentiment-analysis", model=model_name)


def analyze_sentiment(
    df_comments: pd.DataFrame,
    config: SentimentConfig,
    sentiment_pipeline: Callable | None = None,
) -> pd.DataFrame:
    """Adiciona `sentiment_label`/`sentiment_score` a partir de `config.text_column`.

    `sentiment_pipeline`, se informado, substitui o pipeline HuggingFace real
    — usado em testes para não baixar o modelo. Deve ser um callable que,
    dado um texto, retorna `[{"label": ..., "score": ...}]` (mesma
    interface de `transformers.pipeline`)."""
    df = df_comments.copy()

    analisador = sentiment_pipeline or _build_pipeline(config.model_name)

    def _analisar(texto):
        if pd.notna(texto) and str(texto).strip() != "":
            try:
                resultado = analisador(texto, truncation=True, max_length=512)[0]
                return pd.Series([resultado["label"], resultado["score"]])
            except Exception:
                return pd.Series([None, None])
        return pd.Series([None, None])

    df[["sentiment_label", "sentiment_score"]] = df[config.text_column].apply(_analisar)

    return df
