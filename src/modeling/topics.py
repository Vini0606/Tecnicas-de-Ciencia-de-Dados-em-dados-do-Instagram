"""Modelagem de tópicos determinística via BERTopic (sem Gemini)"""

from __future__ import annotations

import ast
import logging
import time
from typing import Any

import numpy as np
import pandas as pd
from bertopic import BERTopic
from bertopic.representation import KeyBERTInspired
from hdbscan import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer

from src.modeling.config import (
    PostTopicModelConfig,
    PreprocessingConfig,
    TopicModelConfig,
)
from src.modeling.preprocessing import preprocess_comments

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


def merge_topic_info(df: pd.DataFrame, document_info: pd.DataFrame) -> pd.DataFrame:
    """Junta por posição (não por índice) o `document_info` do BERTopic a
    `df`, na mesma ordem de `docs` usada em `model_topics`, descartando a
    coluna `Document` (redundante com o texto de origem).

    Mesma lógica de `_merge_topic_info` em `orchestration.py` (comentários)
    -- duplicada aqui, não promovida, porque a consolidação das duas
    chamadas fica para a issue #75 (ADR 0019, parte C), que é quem de fato
    une os dois usos na orquestração."""
    df_reset = df.reset_index(drop=True)
    info_reset = document_info.reset_index(drop=True)
    return pd.concat([df_reset, info_reset], axis=1).drop(columns=["Document"])


def hashtags_to_text(hashtags: Any) -> str:
    """`hashtags` chega do Silver como uma lista serializada em string (ex.:
    `'["politica", "brasil"]'`, ver ADR 0019 parte A) -- extrai as palavras
    como texto plano, sem colchetes/aspas, pra não poluir o vocabulário do
    BERTopic com sintaxe de lista. Nulo/vazio/malformado vira string vazia,
    nunca quebra o ajuste."""
    if not isinstance(hashtags, str) or not hashtags.strip():
        return ""
    try:
        tags = ast.literal_eval(hashtags)
    except (ValueError, SyntaxError):
        return ""
    if not isinstance(tags, list):
        return ""
    return " ".join(str(tag) for tag in tags)


def _build_post_documents(df_posts: pd.DataFrame) -> pd.Series:
    captions = df_posts["caption"].fillna("")
    hashtags_texto = df_posts["hashtags"].apply(hashtags_to_text)
    return (captions + " " + hashtags_texto).str.strip()


def classify_post_topics(
    df_posts: pd.DataFrame,
    config: PostTopicModelConfig,
    preprocessing_config: PreprocessingConfig | None = None,
    embedding_model: Any | None = None,
) -> tuple[BERTopic, pd.DataFrame]:
    """Classifica cada post num tópico (BERTopic sobre `caption`+`hashtags`),
    pro preditor de Tema da regressão de performance-por-post (ADR 0019,
    parte B). Reaproveita `model_topics()` como está -- só uma config e uma
    chamada novas, sem nenhuma mudança na função genérica.

    `df_posts` precisa das colunas `caption` e `hashtags` (Silver, ADR 0019
    parte A); posts com `caption` nula/vazia não quebram o ajuste (viram
    documento vazio ou só hashtags). Retorna o DataFrame de posts com as
    colunas do BERTopic (`Topic`, `Name`, etc.) juntadas por posição."""
    preprocessing_config = preprocessing_config or PreprocessingConfig(text_column="document")
    df_docs = pd.DataFrame({preprocessing_config.text_column: _build_post_documents(df_posts)})
    df_preprocessed = preprocess_comments(df_docs, preprocessing_config)
    docs = list(df_preprocessed["text_demojized"])

    topic_model, _topics, _probs, document_info = model_topics(
        docs, config, embedding_model=embedding_model
    )

    df_final = merge_topic_info(df_posts, document_info)
    return topic_model, df_final
