import numpy as np
import pandas as pd

from src.modeling.clustering import cluster_reels
from src.modeling.config import ClusterConfig


def _reels_com_dois_grupos_separados():
    rng = np.random.default_rng(0)
    grupo_a = rng.normal(loc=0.0, scale=0.3, size=(10, 2))
    grupo_b = rng.normal(loc=10.0, scale=0.3, size=(10, 2))
    pontos = np.vstack([grupo_a, grupo_b])
    return pd.DataFrame(pontos, columns=["PC1_Engajamento_videoPlay", "PC2_videoDuration"])


def test_cluster_reels_adiciona_colunas_esperadas():
    df_reels = _reels_com_dois_grupos_separados()
    config = ClusterConfig(max_evals_per_algo=15, random_state=42, max_n_clusters=5)

    df_out, model, cluster_config, score, algo_name = cluster_reels(df_reels, config)

    expected = {"Clusters (AutoClusterHPO)", "model", "config", "score", "algo_name"}
    assert expected <= set(df_out.columns)
    assert len(df_out) == len(df_reels)
    assert algo_name is not None
    assert score > -np.inf


def test_cluster_reels_broadcasta_o_modelo_vencedor_em_todas_as_linhas():
    """`fit_predict` retorna um único modelo vencedor, não um por linha —
    as colunas escalares devem ficar constantes entre as linhas."""
    df_reels = _reels_com_dois_grupos_separados()
    config = ClusterConfig(max_evals_per_algo=15, random_state=42, max_n_clusters=5)

    df_out, *_ = cluster_reels(df_reels, config)

    assert df_out["algo_name"].nunique() == 1
    assert df_out["score"].nunique() == 1


def test_cluster_reels_encontra_dois_grupos_bem_separados():
    df_reels = _reels_com_dois_grupos_separados()
    config = ClusterConfig(max_evals_per_algo=15, random_state=42, max_n_clusters=5)

    df_out, *_ = cluster_reels(df_reels, config)

    labels = df_out["Clusters (AutoClusterHPO)"]
    assert labels.nunique() >= 2
