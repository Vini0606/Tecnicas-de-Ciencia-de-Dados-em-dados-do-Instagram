"""Modelagem de tópicos determinística via BERTopic (sem Gemini)"""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import pandas as pd
from bertopic import BERTopic
from bertopic.representation import KeyBERTInspired
from hdbscan import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer

from src.modeling.config import TopicModelConfig

logger = logging.getLogger(__name__)


def model_topics(
    docs: list[str],
    config: TopicModelConfig,
    embedding_model: Any | None = None,
) -> tuple[BERTopic, list[int], np.ndarray, pd.DataFrame]:
    """Ajusta um `BERTopic` determinístico (representação via `KeyBERTInspired`,
    não via Gemini) e reduz para `config.nr_topics` tópicos.

    `embedding_model`, se informado, substitui `config.embedding_model` —
    usado em testes para não baixar o modelo de sentence-transformers real.
    Aceita qualquer valor que `BERTopic(embedding_model=...)` aceite (nome de
    modelo, instância de `SentenceTransformer`, ou um embedder customizado)."""
    vectorizer_model = CountVectorizer(token_pattern=config.token_pattern)
    hdbscan_model = HDBSCAN(
        min_cluster_size=config.hdbscan_min_cluster_size,
        min_samples=config.hdbscan_min_samples,
        metric="euclidean",
        cluster_selection_method="eom",
        prediction_data=True,
    )

    topic_model = BERTopic(
        hdbscan_model=hdbscan_model,
        vectorizer_model=vectorizer_model,
        representation_model=KeyBERTInspired(),
        embedding_model=embedding_model or config.embedding_model,
        language=config.language,
        calculate_probabilities=config.calculate_probabilities,
        verbose=config.verbose,
    )

    _topics, probs = topic_model.fit_transform(docs)

    # ADR 0012/0015: `reduce_topics` recalcula a representação inteira mesmo
    # quando não há nada a reduzir (nr_topics >= tópicos atuais) -- comportamento
    # incondicional do BERTopic (`_bertopic.py::_reduce_topics`), não corrigido
    # aqui, só tornado visível.
    n_topics_before = len(topic_model.get_topics())
    is_noop = isinstance(config.nr_topics, int) and config.nr_topics >= n_topics_before
    if is_noop:
        logger.debug(
            "BERTopic.reduce_topics: no-op esperado (tópicos atuais=%d <= "
            "nr_topics=%d), mas o BERTopic recalcula a representação mesmo "
            "assim (achado da ADR 0012).",
            n_topics_before,
            config.nr_topics,
        )
    start = time.monotonic()
    topic_model.reduce_topics(docs, nr_topics=config.nr_topics)
    elapsed = time.monotonic() - start
    logger.debug(
        "BERTopic.reduce_topics levou %.1fs (no-op=%s).", elapsed, is_noop
    )

    # `reduce_topics` não retorna as atribuições atualizadas — o array
    # `_topics` de `fit_transform` fica desatualizado após a redução.
    # `document_info["Topic"]` reflete o estado do modelo pós-redução.
    document_info = topic_model.get_document_info(docs)
    topics = document_info["Topic"].tolist()

    return topic_model, topics, probs, document_info
