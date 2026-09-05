import numpy as np
import pandas as pd
from bertopic.backend import BaseEmbedder

from src.modeling.config import PostTopicModelConfig, TopicModelConfig
from src.modeling.topics import (
    classify_post_topics,
    hashtags_to_text,
    merge_topic_info,
    model_topics,
)

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


def test_model_topics_loga_debug_quando_reduce_topics_e_noop(caplog):
    """ADR 0012/0015: reduce_topics recalcula a representação mesmo quando
    não há nada a reduzir -- essa checagem deve ficar visível em DEBUG."""
    caplog.set_level("DEBUG", logger="src.modeling.topics")
    docs = _docs_sinteticos()
    config = TopicModelConfig(
        hdbscan_min_cluster_size=4,
        hdbscan_min_samples=2,
        nr_topics=10,  # acima dos 4 tópicos que os grupos sintéticos produzem -- no-op.
        calculate_probabilities=False,
        verbose=False,
    )

    model_topics(docs, config, embedding_model=_FakeEmbedder())

    mensagens_noop = [
        r.getMessage() for r in caplog.records if "no-op esperado" in r.getMessage()
    ]
    assert len(mensagens_noop) == 1


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


def test_merge_topic_info_junta_por_posicao_e_descarta_document():
    df = pd.DataFrame({"caption": ["a", "b"]})
    document_info = pd.DataFrame({"Document": ["x", "y"], "Topic": [0, 1], "Name": ["t0", "t1"]})

    resultado = merge_topic_info(df, document_info)

    assert "Document" not in resultado.columns
    assert resultado["Topic"].tolist() == [0, 1]
    assert resultado["caption"].tolist() == ["a", "b"]


def test_hashtags_to_text_extrai_palavras_da_lista_serializada():
    assert hashtags_to_text('["politica", "brasil"]') == "politica brasil"
    assert hashtags_to_text("[]") == ""


def test_hashtags_to_text_trata_nulo_vazio_e_malformado_como_vazio():
    assert hashtags_to_text(None) == ""
    assert hashtags_to_text(np.nan) == ""
    assert hashtags_to_text("") == ""
    assert hashtags_to_text("   ") == ""
    assert hashtags_to_text("não é uma lista") == ""
    # Sintaticamente válido, mas não é uma lista -- não pode virar texto.
    assert hashtags_to_text('"apenas uma string"') == ""


def _df_posts_sinteticos():
    return pd.DataFrame(
        {
            "caption": [
                f"grupo{i} legenda numero {j} sobre o tema {i}"
                for i in range(N_GRUPOS)
                for j in range(DOCS_POR_GRUPO)
            ],
            "hashtags": [None] * (N_GRUPOS * DOCS_POR_GRUPO),
        }
    )


def _post_topic_config():
    return PostTopicModelConfig(
        hdbscan_min_cluster_size=4,
        hdbscan_min_samples=2,
        nr_topics=3,
        calculate_probabilities=False,
        verbose=False,
    )


def test_classify_post_topics_com_embedder_fake_produz_topico_por_post():
    df_posts = _df_posts_sinteticos()

    topic_model, df_final = classify_post_topics(
        df_posts, _post_topic_config(), embedding_model=_FakeEmbedder()
    )

    assert len(df_final) == len(df_posts)
    assert "Topic" in df_final.columns
    assert "Document" not in df_final.columns
    # Colunas originais de df_posts preservadas, na mesma ordem de linhas.
    assert df_final["caption"].tolist() == df_posts["caption"].tolist()
    topicos_nao_ruido = {t for t in df_final["Topic"] if t != -1}
    assert len(topicos_nao_ruido) < N_GRUPOS


def test_classify_post_topics_caption_nula_ou_vazia_nao_quebra():
    df_posts = _df_posts_sinteticos()
    # Últimos dois posts: caption nula (None) e vazia ("") -- nenhum dos
    # dois pode quebrar o ajuste.
    df_posts.loc[len(df_posts) - 1, "caption"] = None
    df_posts.loc[len(df_posts) - 1, "hashtags"] = '["extra"]'
    df_posts.loc[len(df_posts) - 2, "caption"] = ""

    topic_model, df_final = classify_post_topics(
        df_posts, _post_topic_config(), embedding_model=_FakeEmbedder()
    )

    assert len(df_final) == len(df_posts)
