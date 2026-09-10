import numpy as np
import pandas as pd

from src.modeling.config import FeedPCAConfig, PCAConfig
from src.modeling.pca import reduce_dimensions


def test_reduce_dimensions_adiciona_colunas_pc1_pc2():
    df_reels = pd.DataFrame(
        {
            "commentsCount": [1, 2, 3, 100],
            "likesCount": [1, 2, 3, 100],
            "videoPlayCount": [1, 2, 3, 100],
            "videoDuration": [10, 20, 30, 15],
        }
    )
    config = PCAConfig(random_state=42)

    df_out, pca_model = reduce_dimensions(df_reels, config)

    assert {"PC1_Engajamento_videoPlay", "PC2_videoDuration"} <= set(df_out.columns)
    assert len(df_out) == len(df_reels)
    assert pca_model.n_components_ == 2


def test_reduce_dimensions_nao_muta_o_dataframe_original():
    df_reels = pd.DataFrame(
        {
            "commentsCount": [1, 2, 3],
            "likesCount": [1, 2, 3],
            "videoPlayCount": [1, 2, 3],
            "videoDuration": [10, 20, 30],
        }
    )
    config = PCAConfig(random_state=42)

    reduce_dimensions(df_reels, config)

    assert "PC1_Engajamento_videoPlay" not in df_reels.columns


def test_reduce_dimensions_e_deterministico_com_random_state_fixo():
    df_reels = pd.DataFrame(
        {
            "commentsCount": [1, 5, 3, 40, 2],
            "likesCount": [1, 6, 3, 44, 2],
            "videoPlayCount": [1, 5, 3, 39, 2],
            "videoDuration": [10, 22, 30, 15, 12],
        }
    )
    config = PCAConfig(random_state=42)

    df_a, _ = reduce_dimensions(df_reels, config)
    df_b, _ = reduce_dimensions(df_reels, config)

    np.testing.assert_allclose(
        df_a["PC1_Engajamento_videoPlay"].to_numpy(),
        df_b["PC1_Engajamento_videoPlay"].to_numpy(),
    )


def test_reduce_dimensions_com_feed_pca_config_nao_precisa_de_colunas_de_video():
    """ADR 0020 (Ficha 2 / issue #87): posts do feed não têm
    `videoPlayCount`/`videoDuration` -- `FeedPCAConfig` entra só com
    `commentsCount`/`likesCount`, e `reduce_dimensions` (código genérico,
    dirigido por `config.feature_columns`) não pode quebrar por essas
    colunas faltarem."""
    df_posts = pd.DataFrame(
        {
            "commentsCount": [1, 2, 3, 100],
            "likesCount": [1, 2, 3, 100],
        }
    )
    config = FeedPCAConfig(random_state=42)

    df_out, pca_model = reduce_dimensions(df_posts, config)

    assert {"PC1_Engajamento_videoPlay", "PC2_videoDuration"} <= set(df_out.columns)
    assert len(df_out) == len(df_posts)
    assert pca_model.n_components_ == 2
