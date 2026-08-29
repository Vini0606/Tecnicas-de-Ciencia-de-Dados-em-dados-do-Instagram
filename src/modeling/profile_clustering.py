"""
Clusterização de PERFIL de governador (Fase 2), distinta da clusterização de
reel existente em `src/modeling/clustering.py::cluster_reels`. Só 27 linhas
(uma por governador) -- ver `ClusterConfig.max_n_clusters` no chamador para
evitar espaços de busca folgados demais para esse tamanho de amostra.
"""

from __future__ import annotations

import pandas as pd

from src.modeling.clustering import run_autocluster
from src.modeling.config import ClusterConfig


def cluster_governor_profiles(
    df_profiles: pd.DataFrame, config: ClusterConfig
) -> tuple[pd.DataFrame, object, dict | None, float, str | None]:
    """Aplica `run_autocluster` a `df_profiles` (1 linha por governador, ex.
    `governor_engagement`). Ver `run_autocluster` para o formato do retorno."""
    return run_autocluster(df_profiles, config)
