"""Proporções de sentimento sobre os comentários CLASSIFICADOS.

Comentário sem rótulo (texto vazio) fica fora do denominador: não é "não
positivo" nem "não negativo", é não observado. Mesma base da NSM, da dimensão
Qualidade e dos Scores ICE (`src/`)."""

from __future__ import annotations

import pandas as pd


def proporcao_rotulo(rotulos: pd.Series, rotulo: str) -> float:
    """Fração de `rotulo` entre os rótulos não nulos; `NaN` sem nenhum."""
    classificados = rotulos.dropna()
    if classificados.empty:
        return float("nan")
    return float((classificados == rotulo).mean())


def indicador_rotulo(rotulos: pd.Series, rotulo: str) -> pd.Series:
    """1.0/0.0 por linha e `NaN` sem rótulo, para médias que ignoram nulos."""
    return (rotulos == rotulo).astype(float).where(rotulos.notna())
