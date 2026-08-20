"""Pré-processamento de texto dos comentários (stopwords e emojis)"""

from __future__ import annotations

from functools import lru_cache

import emoji
import nltk
import pandas as pd

from src.modeling.config import PreprocessingConfig


@lru_cache(maxsize=None)
def _stopwords(language: str) -> frozenset[str]:
    try:
        words = nltk.corpus.stopwords.words(language)
    except LookupError:
        nltk.download("stopwords")
        words = nltk.corpus.stopwords.words(language)
    return frozenset(words)


def remove_stopwords(texto: str, stopwords: frozenset[str]) -> str:
    if not isinstance(texto, str):
        return ""
    palavras = texto.split()
    return " ".join(p for p in palavras if p.lower() not in stopwords)


def demojize_text(texto: str, language: str = "pt") -> str:
    return emoji.demojize(texto, language=language)


def preprocess_comments(df_comments: pd.DataFrame, config: PreprocessingConfig) -> pd.DataFrame:
    """Remove stopwords e converte emojis em texto, adicionando as colunas
    `text clean` e `text_demojized` a partir de `config.text_column`."""
    df = df_comments.copy()

    stopwords = _stopwords(config.stopwords_language)
    df["text clean"] = df[config.text_column].apply(
        lambda texto: remove_stopwords(texto, stopwords)
    )
    df["text_demojized"] = df["text clean"].apply(
        lambda texto: demojize_text(texto, config.demoji_language)
    )

    return df
