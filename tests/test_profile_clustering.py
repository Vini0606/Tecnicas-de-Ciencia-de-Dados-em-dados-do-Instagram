import numpy as np
import pandas as pd

from src.modeling.clustering import cluster_reels
from src.modeling.config import ClusterConfig
from src.modeling.profile_clustering import cluster_governor_profiles


def _perfis_com_dois_grupos_separados():
    rng = np.random.default_rng(0)
    grupo_a = rng.normal(loc=0.0, scale=0.1, size=(4, 3))
    grupo_b = rng.normal(loc=5.0, scale=0.1, size=(4, 3))
    pontos = np.vstack([grupo_a, grupo_b])
    df = pd.DataFrame(pontos, columns=["% ENGAJAMENTO", "RECENCIA", "FREQUENCIA"])
    df["inputUrl"] = [f"https://www.instagram.com/g{i}/" for i in range(len(df))]
    return df


def test_cluster_governor_profiles_adiciona_colunas_esperadas():
    df_profiles = _perfis_com_dois_grupos_separados()
    config = ClusterConfig(
        feature_columns=["% ENGAJAMENTO", "RECENCIA", "FREQUENCIA"],
        max_evals_per_algo=15,
        random_state=42,
        max_n_clusters=4,
    )

    df_out, model, cluster_config, score, algo_name = cluster_governor_profiles(
        df_profiles, config
    )

    expected = {"Clusters (AutoClusterHPO)", "model", "config", "score", "algo_name"}
    assert expected <= set(df_out.columns)
    assert len(df_out) == len(df_profiles)
    assert "inputUrl" in df_out.columns  # preservada para o writer da Gold
    assert algo_name is not None
    assert score > -np.inf


def test_cluster_governor_profiles_encontra_dois_grupos_bem_separados():
    df_profiles = _perfis_com_dois_grupos_separados()
    config = ClusterConfig(
        feature_columns=["% ENGAJAMENTO", "RECENCIA", "FREQUENCIA"],
        max_evals_per_algo=15,
        random_state=42,
        max_n_clusters=4,
    )

    df_out, *_ = cluster_governor_profiles(df_profiles, config)

    labels = df_out["Clusters (AutoClusterHPO)"]
    assert labels.nunique() >= 2


def test_cluster_governor_profiles_e_cluster_reels_compartilham_a_mesma_logica():
    """`cluster_reels` e `cluster_governor_profiles` são wrappers com nome
    específico sobre `run_autocluster` -- não devem divergir em
    comportamento para o mesmo DataFrame/config."""
    df_profiles = _perfis_com_dois_grupos_separados()
    config = ClusterConfig(
        feature_columns=["% ENGAJAMENTO", "RECENCIA", "FREQUENCIA"],
        max_evals_per_algo=15,
        random_state=42,
        max_n_clusters=4,
    )

    df_via_profiles, *_ = cluster_governor_profiles(df_profiles, config)
    df_via_reels, *_ = cluster_reels(df_profiles, config)

    pd.testing.assert_series_equal(
        df_via_profiles["Clusters (AutoClusterHPO)"],
        df_via_reels["Clusters (AutoClusterHPO)"],
    )
