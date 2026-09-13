"""Cálculo de variação vs. execução anterior (ADR 0021 / issue #110).

Chamado "run-over-run" no conceito, não "semana-a-semana": o pipeline não
tem agendamento fixo hoje (execuções são manuais/ad hoc -- o agendamento via
lambda AWS é item pendente, ver ADR 0021, ponto de atrito 4), então "última
execução vs. anterior" pode significar dias ou meses de intervalo, nunca uma
semana garantida. O nome público `week_over_week` é mantido por brevidade
(mesma decisão da issue #110) -- o que importa é o comportamento abaixo, não
o nome da função.
"""

from __future__ import annotations

import pandas as pd

# Limiar de alerta de negatividade (ADR 0021 / issue #111). Definido aqui, e
# não em `dashboard/screens/radar.py`, porque a Tela 1 ("Resumo da semana",
# issue #111) precisa dele para a faixa de decisão semafórica ANTES da Tela 3
# ("Radar de crise", issue #113) existir -- ver issue #111, user story 3
# ("mesmo critério da Tela 3"). Quando a issue #113 for implementada, ela
# deve IMPORTAR esta constante (`from dashboard.core.deltas import
# LIMIAR_NEGATIVIDADE_ALERTA`), nunca redefinir um segundo valor: as duas
# telas precisam concordar sobre o que conta como "crise" sem exigir que a
# analista de assessoria memorize dois números diferentes para o mesmo
# conceito.
#
# 0.30 (30% dos comentários avaliados como negativos) é um ponto de partida
# documentado, não calibrado contra dado real: o projeto ainda não acumulou
# histórico suficiente para justificar um limiar orientado a dado (mesma
# limitação já registrada para CMGR/retenção em `governor_growth_metrics`,
# ver `GOLD_GROWTH_METRICS_SCHEMA` / ADR 0020 Ficha 7). Escolhido por ser
# redondo e fácil de explicar ("quase 1 em cada 3 comentários é negativo") --
# revisar quando a Tela 3 tiver dado real suficiente para recalibrar.
LIMIAR_NEGATIVIDADE_ALERTA = 0.30


def week_over_week(
    df_history: pd.DataFrame,
    value_col: str,
    key_col: str = "inputUrl",
    run_col: str = "_run_id",
) -> dict[object, tuple[object, float | None]] | None:
    """Compara as 2 execuções mais recentes de `df_history` por `run_col`,
    pivotando por `key_col`. Retorna `{chave: (valor_atual, delta_percentual)}`.

    - Retorna `None` se houver menos de 2 execuções no histórico -- a tela
      deve ocultar a seta de variação nesse caso, nunca mostrar "0%".
    - Uma chave ausente na execução anterior, ou com valor anterior nulo/zero
      (divisão por zero), recebe `delta_percentual=None` -- documentado,
      nunca levanta exceção.
    """
    if df_history.empty or run_col not in df_history.columns:
        return None

    runs = sorted(df_history[run_col].unique())
    if len(runs) < 2:
        return None
    atual_id, anterior_id = runs[-1], runs[-2]

    serie_atual = (
        df_history[df_history[run_col] == atual_id]
        .drop_duplicates(subset=[key_col], keep="last")
        .set_index(key_col)[value_col]
    )
    serie_anterior = (
        df_history[df_history[run_col] == anterior_id]
        .drop_duplicates(subset=[key_col], keep="last")
        .set_index(key_col)[value_col]
    )

    resultado: dict[object, tuple[object, float | None]] = {}
    for chave, valor_atual in serie_atual.items():
        if chave not in serie_anterior.index:
            resultado[chave] = (valor_atual, None)
            continue
        valor_anterior = serie_anterior.loc[chave]
        if pd.isna(valor_anterior) or valor_anterior == 0:
            resultado[chave] = (valor_atual, None)
            continue
        delta_percentual = (valor_atual - valor_anterior) / valor_anterior * 100
        resultado[chave] = (valor_atual, delta_percentual)
    return resultado


def run_dates(
    df_history: pd.DataFrame,
    run_col: str = "_run_id",
    timestamp_col: str = "_generated_at",
) -> tuple[object, object] | None:
    """Datas reais (não os `_run_id`s) das 2 execuções mais recentes de
    `df_history`, na ordem `(anterior, atual)` -- para a tela exibir
    "vs. coleta de DD/MM" em vez de "vs. semana anterior" (ver ADR 0021,
    ponto de atrito 4). Retorna `None` se houver menos de 2 execuções."""
    if df_history.empty or run_col not in df_history.columns:
        return None

    runs = sorted(df_history[run_col].unique())
    if len(runs) < 2:
        return None
    atual_id, anterior_id = runs[-1], runs[-2]

    data_atual = df_history.loc[df_history[run_col] == atual_id, timestamp_col].iloc[0]
    data_anterior = df_history.loc[df_history[run_col] == anterior_id, timestamp_col].iloc[0]
    return data_anterior, data_atual
