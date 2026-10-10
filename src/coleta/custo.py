"""Estimativa de custo (US$, pior caso) de um Recorte nas três coleções pagas
(posts, reels, UGC). Mesmas fórmulas calibradas de `scripts/apify_backfill_shared`."""

from __future__ import annotations

from datetime import date

from config import settings
from scripts.apify_backfill_shared import (
    default_results_limit,
    estimate_cost_usd,
    estimate_cost_usd_for_results_limit,
)
from src.coleta.recorte import Recorte


def teto_efetivo(recorte: Recorte, hoje: date) -> int:
    """Teto informado; senão, com janela, o padrão por janela do backfill;
    senão, o padrão do projeto."""
    if recorte.teto is not None:
        return recorte.teto
    dias = recorte.dias_a_extrair(hoje)
    return default_results_limit(dias) if dias else settings.RESULTS_LIMIT


def estimar_custo(recorte: Recorte, n_governadores: int, hoje: date) -> dict[str, float]:
    teto = teto_efetivo(recorte, hoje)
    ugc = estimate_cost_usd_for_results_limit(teto, n_governadores, media_types=1)
    dias = recorte.dias_a_extrair(hoje)
    if dias:
        posts_reels = estimate_cost_usd(dias, n_governadores)
        total = round(posts_reels + ugc, 2)
    else:
        posts_reels = estimate_cost_usd_for_results_limit(teto, n_governadores, media_types=2)
        total = estimate_cost_usd_for_results_limit(teto, n_governadores, media_types=3)
    return {"posts_reels": posts_reels, "ugc": ugc, "total": total}
