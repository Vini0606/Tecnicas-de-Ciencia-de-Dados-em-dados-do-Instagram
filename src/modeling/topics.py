"""Modelagem de tópicos determinística via BERTopic (sem Gemini)"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from bertopic import BERTopic
from bertopic.representation import KeyBERTInspired
from hdbscan import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer

from src.modeling.config import TopicModelConfig


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
    topic_model.reduce_topics(docs, nr_topics=config.nr_topics)

    # `reduce_topics` não retorna as atribuições atualizadas — o array
    # `_topics` de `fit_transform` fica desatualizado após a redução.
    # `document_info["Topic"]` reflete o estado do modelo pós-redução.
    document_info = topic_model.get_document_info(docs)
    topics = document_info["Topic"].tolist()

    return topic_model, topics, probs, document_info
