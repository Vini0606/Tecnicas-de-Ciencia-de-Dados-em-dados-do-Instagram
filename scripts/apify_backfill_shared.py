"""
Helpers compartilhados entre `scripts/run_apify_calibration_test.py` e
`scripts/run_apify_backfill.py` -- estimativa de custo, limite de resultados
escalavel e carregamento dos links dos governadores. Nao e um script
executavel, so um modulo de import.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

import pandas as pd

from config import settings

DEFAULT_DAYS = 90

# Baseline calculado na sessao de 2026-08-29 a partir da amostra atual (30
# itens mais recentes por governador) -- ver handoff. E o que o teste de
# calibracao confirma ou corrige, independente da janela (--days) escolhida.
BASELINE_REELS_PER_DAY = 1.65
BASELINE_POSTS_PER_DAY = 2.60

# resultsLimit e aplicado POR PERFIL pela Apify, nao no total do run -- se o
# default fosse fixo (ex: 1000), uma janela grande (--days 365+) trunca
# silenciosamente qualquer governador acima da media, subestimando a
# calibracao/backfill sem avisar. Escala com --days usando uma margem de
# seguranca bem acima do baseline conhecido (4.25 itens/dia/governador).
RESULTS_LIMIT_SAFETY_MARGIN_PER_DAY = 10
RESULTS_LIMIT_FLOOR = 200

# Plano Starter da Apify usado nas estimativas de custo do backfill.
STARTER_PRICE_PER_1000_RESULTS = 2.30


def default_results_limit(days: int) -> int:
    return max(RESULTS_LIMIT_FLOOR, days * RESULTS_LIMIT_SAFETY_MARGIN_PER_DAY)


def profiles_hitting_limit(items: list[dict], results_limit: int) -> list[str]:
    """Perfis cujo total de itens retornados bateu exatamente no resultsLimit
    -- sinal de que o numero real e maior e o resultado foi truncado."""
    counts: dict[str, int] = {}
    for item in items:
        key = item.get("inputUrl") or item.get("ownerUsername") or "desconhecido"
        counts[key] = counts.get(key, 0) + 1
    return sorted(key for key, count in counts.items() if count >= results_limit)


def load_links() -> list[str]:
    df_gov = pd.read_excel(settings.GOVERNADORES_FILE)
    df_gov.columns = df_gov.columns.str.strip()
    return list(df_gov[settings.LINK_COLUMN].str.strip().unique())


def estimate_cost_usd(days: int, n_governors: int) -> float:
    """Estimativa PRE-run baseada no baseline conhecido -- o resultado real so
    sai depois de chamar a Apify. Usada so pro aviso de confirmacao do --yes."""
    estimated_results = (BASELINE_REELS_PER_DAY + BASELINE_POSTS_PER_DAY) * days * n_governors
    return round(estimated_results / 1000 * STARTER_PRICE_PER_1000_RESULTS, 2)


def project_backfill_costs(total_results: int, days: int) -> dict[int, float]:
    """Extrapola o total de resultados calibrado (na janela rodada) para
    janelas de 1-4 anos e converte em custo estimado no plano Starter."""
    daily_rate = total_results / days
    projections = {}
    for years in (1, 2, 3, 4):
        year_days = 365 * years
        total_results_year = daily_rate * year_days
        cost = total_results_year / 1000 * STARTER_PRICE_PER_1000_RESULTS
        projections[years] = round(cost, 2)
    return projections
