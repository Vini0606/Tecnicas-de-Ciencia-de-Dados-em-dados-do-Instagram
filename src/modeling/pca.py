"""PCA de engajamento/duração dos reels"""

from __future__ import annotations

import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from src.modeling.config import PCAConfig


def reduce_dimensions(df_reels: pd.DataFrame, config: PCAConfig) -> tuple[pd.DataFrame, PCA]:
    """Reduz `config.feature_columns` a `config.n_components` componentes principais.

    Adiciona as colunas `PC1_Engajamento_videoPlay` e `PC2_videoDuration`
    (nomes fixos, usados pelas etapas seguintes de clusterização)."""
    df = df_reels.copy()

    X = df[config.feature_columns]
    X_scaled = StandardScaler().fit_transform(X)

    pca_model = PCA(n_components=config.n_components, random_state=config.random_state)
    components = pca_model.fit_transform(X_scaled)

    df["PC1_Engajamento_videoPlay"] = components[:, 0]
    df["PC2_videoDuration"] = components[:, 1]

    return df, pca_model
