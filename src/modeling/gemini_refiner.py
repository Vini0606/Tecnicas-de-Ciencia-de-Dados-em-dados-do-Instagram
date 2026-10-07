"""Refinamento manual dos rótulos de tópico via Gemini"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Mapping

import google.generativeai as genai
import pandas as pd
from bertopic import BERTopic
from bertopic.representation import BaseRepresentation
from scipy.sparse import csr_matrix

from src.modeling.config import GeminiRefinerConfig
from src.modeling.topic_labels import DEGENERATE_TOPIC_LABEL

DEFAULT_PROMPT_TEMPLATE = (
    "Escreva uma descrição de um parágrafo que descreva detalhadamente o que os "
    "comentários do instagram presentes neste tópico tem em comum: {documents}"
)


DISCOURSE_PROMPT_TEMPLATE = (
    "Os textos abaixo são legendas (ou falas transcritas) de posts e reels de "
    "um governador no Instagram, agrupados por assunto parecido. Responda "
    "APENAS com um rótulo curto (no máximo 6 palavras, sem aspas nem "
    "pontuação final) que nomeie o assunto em comum desses textos: {documents}"
)

# `DEGENERATE_TOPIC_LABEL` vive em `topic_labels` (sem dependência de NLP) para
# o dashboard usá-lo sem importar bertopic; segue exportado daqui.

_WORD_RE = re.compile(r"[^\W\d_]{2,}")


def is_degenerate_topic(keywords: list[tuple[str, float]]) -> bool:
    """True se nenhuma keyword do tópico contém uma palavra de verdade
    (2+ letras) -- só vazio, underscores ou dígitos."""
    return not any(_WORD_RE.search(str(word)) for word, _score in keywords)


class GeminiDocsRefiner(BaseRepresentation):
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        prompt_template: str | None = None,
        sleep_seconds: int = 60,
        sleep_every_n_topics: int = 10,
    ):
        genai.configure(api_key=api_key)
        self.model = model
        self.prompt_template = prompt_template or DEFAULT_PROMPT_TEMPLATE
        self.sleep_seconds = sleep_seconds
        self.sleep_every_n_topics = sleep_every_n_topics

    def extract_topics(
        self,
        topic_model,
        documents: pd.DataFrame,
        c_tf_idf: csr_matrix,
        topics: Mapping[str, list[tuple[str, float]]],
    ) -> Mapping[str, list[tuple[str, float]]]:
        updated_topics = {}
        docs_per_topic = documents.groupby(["Topic"])["Document"].apply(list)

        for topic_id, keywords in topics.items():
            if topic_id == -1:
                updated_topics[topic_id] = keywords
                continue
            if is_degenerate_topic(keywords):
                updated_topics[topic_id] = [(DEGENERATE_TOPIC_LABEL, 1.0)] + keywords
                continue
            if self.sleep_every_n_topics and topic_id % self.sleep_every_n_topics == 0:
                time.sleep(self.sleep_seconds)
            try:
                topic_docs = docs_per_topic.get(topic_id, [])
                if not topic_docs:
                    updated_topics[topic_id] = keywords
                    continue
                sample_size = min(len(topic_docs), 10)
                docs_sample = "\n- ".join(random.sample(topic_docs, sample_size))
                prompt = self.prompt_template.format(documents=docs_sample)
                response = genai.GenerativeModel(self.model).generate_content(prompt)
                label = response.text.strip() if hasattr(response, "text") else None
                if label:
                    updated_topics[topic_id] = [(label, 1.0)] + keywords
                else:
                    updated_topics[topic_id] = keywords
            except Exception as e:  # noqa: BLE001 -- qualquer falha da API do Gemini cai no fallback abaixo
                print(f"[GeminiDocsRefiner] Erro no tópico {topic_id}: {e}")
                updated_topics[topic_id] = keywords
        return updated_topics


def apply_gemini_refinement(
    topic_model: BERTopic,
    docs: list[str],
    config: GeminiRefinerConfig,
    prompt_template: str | None = None,
) -> BERTopic:
    """Recalcula só as representações de tópico via Gemini, reaproveitando a
    clusterização já ajustada (sem refazer embeddings/UMAP/HDBSCAN) — ao
    contrário de passar `GeminiDocsRefiner` no construtor do `BERTopic`, que
    dispararia a API duas vezes (em `fit_transform` e em `reduce_topics`)."""
    refiner = GeminiDocsRefiner(
        api_key=config.api_key,
        model=config.model,
        prompt_template=prompt_template or config.prompt_template,
        sleep_seconds=config.sleep_seconds,
        sleep_every_n_topics=config.sleep_every_n_topics,
    )
    topic_model.update_topics(docs, representation_model=refiner)
    return topic_model
