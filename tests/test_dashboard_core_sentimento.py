"""As proporções do painel usam só os comentários classificados (mesma base do `src/`)."""

import math

import pandas as pd
import pytest

from dashboard.core.deltas import aggregate_pct_negative_by_publication_day
from dashboard.core.sentimento import indicador_rotulo, proporcao_rotulo
from dashboard.screens.resumo_funil import (
    _agregar_pct_negativo_por_run,
    _proporcao_negativo,
    _proporcao_negativo_media_por_governador,
)

ROTULOS = ["positive", "negative", None, None]


def test_proporcao_ignora_sem_rotulo():
    assert proporcao_rotulo(pd.Series(ROTULOS), "positive") == 0.5


def test_proporcao_sem_nenhum_rotulo_e_nan():
    assert math.isnan(proporcao_rotulo(pd.Series([None, None], dtype=object), "positive"))


def test_indicador_deixa_nulo_sem_rotulo():
    assert indicador_rotulo(pd.Series(ROTULOS), "negative").mean() == 0.5


def test_funil_usa_classificados():
    df = pd.DataFrame({"sentiment_label": ROTULOS, "_chave": "g", "_run_id": "r"})
    assert _proporcao_negativo(df) == 0.5
    assert _proporcao_negativo_media_por_governador(df) == 0.5
    for todos in (False, True):
        assert _agregar_pct_negativo_por_run(df, todos=todos)["pct_negativo"].tolist() == [0.5]


def test_funil_sem_nenhum_classificado_e_none():
    assert _proporcao_negativo(pd.DataFrame({"sentiment_label": [None]})) is None


def test_serie_por_dia_usa_classificados():
    df = pd.DataFrame(
        {
            "sentiment_label": ROTULOS,
            "id_comment": list("abcd"),
            "_run_id": "r",
            "timestamp": "2026-10-01T10:00:00.000Z",
        }
    )
    out = aggregate_pct_negative_by_publication_day(df)
    assert out["pct_negativo"].tolist() == pytest.approx([0.5])
