"""
Módulo de compatibilidade para visualizações de dados.

Este arquivo existe para garantir retrocompatibilidade com código legado que
importa de `src.visualization.visualize`. O código novo deve importar diretamente
de `src.visualization.charts`.

Todas as funções de visualização estão centralizadas em `charts.py` e
rexportadas aqui por conveniência.
"""

from src.visualization.charts import (
    plot_correlation_heatmap,  # noqa: F401
    plot_dual_axis,  # noqa: F401
    plot_scatter,  # noqa: F401
    plot_top5_bar,  # noqa: F401
    plot_top_n_bar,  # noqa: F401
)
