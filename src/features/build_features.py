"""
Módulo de agregação para engenharia de features.

Este módulo rexporta as classes de transformação de features de submodulos,
aplicando o princípio de Single Responsibility (SRP):

- `EngagementFeatureBuilder` (em `engagement.py`) — calcula RFM e métricas de engajamento
- `CommentsTransformer` (em `comments.py`) — processa e normaliza comentários aninhados

O código novo deve importar diretamente dos submodulos, mas notebooks legados
podem usar este módulo como entry point.
"""

from src.features.comments import CommentsTransformer  # noqa: F401
from src.features.engagement import EngagementFeatureBuilder  # noqa: F401
