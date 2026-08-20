from unittest.mock import MagicMock

import hdbscan
import numpy as np
import pandas as pd
import pytest
from bertopic import BERTopic
from bertopic.backend import BaseEmbedder
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

from src.modeling.checkpoint import load_checkpoint, save_checkpoint


class _FakeEmbedder(BaseEmbedder):
    def embed(self, documents, verbose: bool = False):
        rng = np.random.default_rng(0)
        return rng.normal(size=(len(documents), 5))


def _fit_tiny_topic_model():
    docs = [f"doc numero {i} sobre tema {i % 3}" for i in range(15)]
    topic_model = BERTopic(
        embedding_model=_FakeEmbedder(),
        calculate_probabilities=False,
        verbose=False,
        hdbscan_model=hdbscan.HDBSCAN(min_cluster_size=3, min_samples=1),
    )
    topic_model.fit_transform(docs)
    return topic_model, docs


def _df_comments(docs, topic_model):
    info = topic_model.get_document_info(docs)
    df = pd.DataFrame({"text_demojized": docs, "id_comment": [str(i) for i in range(len(docs))]})
    return pd.concat([df.reset_index(drop=True), info.reset_index(drop=True)], axis=1)


def _df_reels():
    return pd.DataFrame(
        {
            "id": ["r1", "r2"],
            "ownerUsername": ["gov_a", "gov_b"],
            "PC1_Engajamento_videoPlay": [0.1, 0.2],
            "PC2_videoDuration": [1.0, 2.0],
            "Clusters (AutoClusterHPO)": [0, 1],
            # 'model'/'config' reproduzem o que cluster_reels realmente produz:
            # objeto sklearn cru e dict, broadcast em toda linha.
            "model": [None, None],
            "config": [{"n_clusters": 2}, {"n_clusters": 2}],
            "score": [0.5, 0.5],
            "algo_name": ["KMeans", "KMeans"],
        }
    )


def test_save_checkpoint_grava_todos_os_artefatos(tmp_path):
    topic_model, docs = _fit_tiny_topic_model()
    df_comments = _df_comments(docs, topic_model)
    pca_model = PCA(n_components=2).fit(np.random.rand(10, 4))
    cluster_model = KMeans(n_clusters=2, n_init="auto").fit(np.random.rand(10, 2))

    checkpoint_dir = save_checkpoint(
        "run_teste",
        topic_model=topic_model,
        df_comments=df_comments,
        df_reels=_df_reels(),
        pca_model=pca_model,
        pca_feature_columns=["commentsCount", "likesCount", "videoPlayCount", "videoDuration"],
        cluster_model=cluster_model,
        cluster_config={"n_clusters": 2},
        cluster_score=0.42,
        cluster_algo_name="KMeans",
        embedding_model_name="modelo-fake",
        checkpoints_dir=tmp_path,
    )

    assert checkpoint_dir == tmp_path / "run_teste"
    assert (checkpoint_dir / "topic_model").exists()
    assert (checkpoint_dir / "df_comments.parquet").exists()
    assert (checkpoint_dir / "df_reels.parquet").exists()
    assert (checkpoint_dir / "pca_model.joblib").exists()
    assert (checkpoint_dir / "cluster_model.joblib").exists()
    assert (checkpoint_dir / "metadata.json").exists()


def test_save_checkpoint_descarta_colunas_model_config_do_df_reels(tmp_path):
    """'model'/'config' (de cluster_reels) carregam objeto sklearn/dict cru
    -- não são serializáveis em parquet e são redundantes com
    cluster_model.joblib/metadata.json."""
    topic_model, docs = _fit_tiny_topic_model()
    df_comments = _df_comments(docs, topic_model)

    save_checkpoint(
        "run_teste",
        topic_model=topic_model,
        df_comments=df_comments,
        df_reels=_df_reels(),
        pca_model=PCA(n_components=2).fit(np.random.rand(10, 4)),
        pca_feature_columns=["a", "b", "c", "d"],
        cluster_model=KMeans(n_clusters=2, n_init="auto").fit(np.random.rand(10, 2)),
        cluster_config={},
        cluster_score=0.1,
        cluster_algo_name="KMeans",
        embedding_model_name="modelo-fake",
        checkpoints_dir=tmp_path,
    )

    df_reels_persistido = pd.read_parquet(tmp_path / "run_teste" / "df_reels.parquet")
    assert "model" not in df_reels_persistido.columns
    assert "config" not in df_reels_persistido.columns


def test_load_checkpoint_reconstroi_docs_e_metadados(tmp_path, monkeypatch):
    topic_model, docs = _fit_tiny_topic_model()
    df_comments = _df_comments(docs, topic_model)

    save_checkpoint(
        "run_teste",
        topic_model=topic_model,
        df_comments=df_comments,
        df_reels=_df_reels(),
        pca_model=PCA(n_components=2).fit(np.random.rand(10, 4)),
        pca_feature_columns=["commentsCount", "likesCount", "videoPlayCount", "videoDuration"],
        cluster_model=KMeans(n_clusters=2, n_init="auto").fit(np.random.rand(10, 2)),
        cluster_config={"n_clusters": 2},
        cluster_score=0.42,
        cluster_algo_name="KMeans",
        embedding_model_name="modelo-fake",
        checkpoints_dir=tmp_path,
    )

    # BERTopic.load tentaria baixar 'modelo-fake' do HuggingFace Hub -- não
    # é um modelo real, então stubamos só essa reconstrução. O resto do
    # load_checkpoint (parquet/joblib/json) roda de verdade.
    fake_loaded_model = MagicMock(name="loaded_topic_model")
    monkeypatch.setattr(
        "src.modeling.checkpoint.BERTopic.load",
        staticmethod(lambda path, embedding_model=None: fake_loaded_model),
    )

    checkpoint = load_checkpoint("run_teste", checkpoints_dir=tmp_path)

    assert checkpoint.topic_model is fake_loaded_model
    assert checkpoint.docs == docs
    assert len(checkpoint.df_comments) == len(docs)
    assert list(checkpoint.df_reels["id"]) == ["r1", "r2"]
    assert checkpoint.pca_feature_columns == [
        "commentsCount",
        "likesCount",
        "videoPlayCount",
        "videoDuration",
    ]
    assert checkpoint.cluster_score == 0.42
    assert checkpoint.cluster_algo_name == "KMeans"
    assert checkpoint.embedding_model_name == "modelo-fake"
    assert isinstance(checkpoint.pca_model, PCA)
    assert isinstance(checkpoint.cluster_model, KMeans)


def test_load_checkpoint_falha_com_mensagem_clara_se_run_id_nao_existe(tmp_path):
    with pytest.raises(FileNotFoundError, match="run_id_inexistente"):
        load_checkpoint("run_id_inexistente", checkpoints_dir=tmp_path)
