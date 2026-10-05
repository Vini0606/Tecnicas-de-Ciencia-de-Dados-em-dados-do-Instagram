"""Issue #186: o checkpoint persiste modelo/documentos de discurso."""

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

from src.modeling.checkpoint import load_checkpoint, save_checkpoint
from tests.test_checkpoint import _df_comments, _df_reels, _fit_tiny_topic_model


def _save_kwargs(tmp_path, topic_model, docs):
    return {
        "topic_model": topic_model,
        "df_comments": _df_comments(docs, topic_model),
        "df_reels": _df_reels(),
        "pca_model": PCA(n_components=2).fit(np.random.rand(10, 4)),
        "pca_feature_columns": ["a", "b", "c", "d"],
        "cluster_model": KMeans(n_clusters=2, n_init="auto").fit(np.random.rand(10, 2)),
        "cluster_config": {},
        "cluster_score": 0.1,
        "cluster_algo_name": "KMeans",
        "embedding_model_name": "modelo-fake",
        "checkpoints_dir": tmp_path,
    }


def test_checkpoint_persiste_modelo_e_documentos_de_discurso(tmp_path, monkeypatch):
    topic_model, docs = _fit_tiny_topic_model()
    discourse_model, discourse_docs = _fit_tiny_topic_model()
    df_discourse = pd.DataFrame(
        {
            "id_reel": [str(i) for i in range(len(discourse_docs))],
            "text": discourse_docs,
            "fonte": "legenda",
            "Topic": 0,
            "Name": "0_x",
        }
    )

    save_checkpoint(
        "run_teste",
        discourse_topic_model=discourse_model,
        df_discourse=df_discourse,
        discourse_embedding_model_name="modelo-discurso",
        **_save_kwargs(tmp_path, topic_model, docs),
    )

    loaded_with = {}

    def _fake_load(path, embedding_model=None):
        loaded_with[path.replace("\\", "/").split("/")[-1]] = embedding_model
        return MagicMock()

    monkeypatch.setattr(
        "src.modeling.checkpoint.BERTopic.load", staticmethod(_fake_load)
    )

    checkpoint = load_checkpoint("run_teste", checkpoints_dir=tmp_path)

    assert checkpoint.discourse_topic_model is not None
    assert checkpoint.docs_discourse == discourse_docs
    assert list(checkpoint.df_discourse["Name"].unique()) == ["0_x"]
    assert loaded_with["discourse_topic_model"] == "modelo-discurso"
    assert loaded_with["topic_model"] == "modelo-fake"


def test_checkpoint_antigo_sem_discurso_carrega_com_discurso_nulo(
    tmp_path, monkeypatch
):
    topic_model, docs = _fit_tiny_topic_model()
    save_checkpoint("run_teste", **_save_kwargs(tmp_path, topic_model, docs))
    monkeypatch.setattr(
        "src.modeling.checkpoint.BERTopic.load",
        staticmethod(lambda path, embedding_model=None: MagicMock()),
    )

    checkpoint = load_checkpoint("run_teste", checkpoints_dir=tmp_path)

    assert checkpoint.discourse_topic_model is None
    assert checkpoint.df_discourse is None
    assert checkpoint.docs_discourse == []
