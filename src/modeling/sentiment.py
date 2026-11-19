"""Análise de sentimento dos comentários"""

from __future__ import annotations

from collections.abc import Callable

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
            except Exception:  # noqa: BLE001 -- qualquer falha do pipeline de inferência cai no fallback abaixo
                return pd.Series([None, None])
        return pd.Series([None, None])

    # Cada texto distinto passa pelo modelo UMA vez: o classificador é
    # determinístico por texto e, em corpora de comentários, metade das
    # linhas repete um texto já visto (aplausos, emojis) -- na Coleta do TCC,
    # 75,6 mil comentários têm 38,6 mil textos únicos. O resultado por linha
    # é idêntico ao de classificar linha a linha; só o tempo muda.
    textos = df[config.text_column]
    resultados_por_texto = {
        texto: _analisar(texto) for texto in pd.unique(textos.dropna())
    }
    vazio = pd.Series([None, None])

    def _consultar(texto):
        if pd.isna(texto):
            return vazio
        return resultados_por_texto.get(texto, vazio)

    df[["sentiment_label", "sentiment_score"]] = textos.apply(_consultar)

    return df
