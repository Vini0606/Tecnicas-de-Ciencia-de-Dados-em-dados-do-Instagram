import numpy as np
from bertopic.backend import BaseEmbedder

from src.modeling.config import TopicModelConfig
from src.modeling.topics import model_topics

N_GRUPOS = 4
DOCS_POR_GRUPO = 8


class _FakeEmbedder(BaseEmbedder):
    """Embedder determinístico: projeta cada documento perto de um dos
    N_GRUPOS cantos de um espaço de baixa dimensão, a partir do marcador
    'grupoN' no próprio texto — dispensa baixar um modelo real."""

    def __init__(self, dim: int = 5):
        super().__init__()
        self.dim = dim

    def embed(self, documents, verbose: bool = False):
        vetores = []
        for doc in documents:
            base = np.zeros(self.dim)
            for i in range(N_GRUPOS):
                if f"grupo{i}" in doc:
                    base[i % self.dim] = 10.0
                    break
            rng = np.random.default_rng(abs(hash(doc)) % (2**32))
            vetores.append(base + rng.normal(scale=0.1, size=self.dim))
        return np.array(vetores)


def _docs_sinteticos():
    return [
        f"grupo{i} comentario numero {j} sobre o tema {i}"
        for i in range(N_GRUPOS)
        for j in range(DOCS_POR_GRUPO)
    ]


def test_model_topics_com_embedder_fake_encontra_multiplos_topicos():
    docs = _docs_sinteticos()
    config = TopicModelConfig(
        hdbscan_min_cluster_size=4,
        hdbscan_min_samples=2,
        nr_topics=3,
        calculate_probabilities=False,
        verbose=False,
    )

    topic_model, topics, probs, document_info = model_topics(
        docs, config, embedding_model=_FakeEmbedder()
    )

    assert len(topics) == len(docs)
    assert len(document_info) == len(docs)
    # Os 4 grupos sintéticos, bem separados, produzem 4 tópicos não-ruído
    # antes da redução; nr_topics=3 deve ter mesclado pelo menos um par.
    topicos_nao_ruido = {t for t in topics if t != -1}
    assert len(topicos_nao_ruido) < N_GRUPOS
    # `topics` (pós-redução, via document_info) deve bater com o Topic
    # reportado por document_info — não pode ficar com o array desatualizado
    # de antes de `reduce_topics`.
    assert topics == document_info["Topic"].tolist()


def test_model_topics_retorna_document_info_com_colunas_esperadas():
    docs = _docs_sinteticos()
    config = TopicModelConfig(
        hdbscan_min_cluster_size=4,
        hdbscan_min_samples=2,
        nr_topics=3,
        calculate_probabilities=False,
        verbose=False,
    )

    _, _, _, document_info = model_topics(docs, config, embedding_model=_FakeEmbedder())

    assert {"Document", "Topic", "Name"} <= set(document_info.columns)
