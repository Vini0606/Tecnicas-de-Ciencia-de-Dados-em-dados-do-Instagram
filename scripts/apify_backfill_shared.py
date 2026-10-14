"""
Helpers compartilhados entre `src/coleta/custo.py` e `src/coleta/cli.py` -- estimativa de custo, limite de resultados
escalavel e carregamento dos links dos governadores. Nao e um script
executavel, so um modulo de import.
"""

import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

import pandas as pd

from config import settings

DEFAULT_DAYS = 90

# Taxas diarias por governador, calibradas em execucao real com 26 governadores
# (ADR 0012): razao de totais `itens / (dias * governadores)`, media que assume
# taxa constante. Substituem o baseline anterior (2,60 posts e 1,65 reels, extrapolado
# dos 30 itens mais recentes por governador em 2026-08-29), que ficou ~3x abaixo.
# Reverificar com a Coleta de 90 dias.
TAXA_REELS_POR_DIA = 5.19
TAXA_POSTS_POR_DIA = 7.22

# resultsLimit e aplicado POR PERFIL pela Apify, nao no total do run -- se o
# default fosse fixo (ex: 1000), uma janela grande (--days 365+) trunca
# silenciosamente qualquer governador acima da media, subestimando a
# calibracao/backfill sem avisar. Escala com --days usando uma margem de
# seguranca acima da taxa calibrada de cada colecao (7.22 posts e 5.19 reels
# por dia por governador; o limite vale por colecao, nao pela soma).
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
    links = df_gov[settings.LINK_COLUMN].str.strip()
    # Um governador pode ficar temporariamente sem conta de Instagram
    # rastreável (ex.: sucessão para um titular interino sem perfil público) --
    # a linha continua em governadores.xlsx para registro/documentação, mas
    # `Link` fica em branco. Sem este filtro, a célula vazia vira o texto
    # literal "nan" (cast de NaN para string) e é tratada como URL real tanto
    # aqui quanto em GovernorsMetadataCleaner.
    links = links[links.notna() & (links.str.len() > 0)]
    return list(links.unique())


def _username_from_url(url: str) -> str:
    """Extrai o username puro de uma URL de perfil do Instagram, robusto a
    query string (`?hl=en`, visto em dado real) e a segmentos extras de path
    (`/reels/`, achado real -- ver PR #132) -- sempre o primeiro segmento
    depois do domínio."""
    path = urlparse(url).path
    return path.strip("/").split("/")[0]


def load_governor_usernames() -> list[str]:
    """Usernames (não URLs) dos governadores atualmente rastreáveis --
    mesma fonte de `load_links()` (já filtra `Link` em branco/NaN, ver ADR
    de sucessão do RJ), só que extraindo o username de cada URL. Usado para
    filtrar Silver/Gold contra `governadores.xlsx` atual (achado: um
    governador removido da planilha continuava vazando dado cada vez mais
    velho em Silver/Gold indefinidamente -- ver PR #137)."""
    return [_username_from_url(link) for link in load_links()]


def estimate_cost_usd(days: int, n_governors: int) -> float:
    """Estimativa PRE-run baseada no baseline conhecido -- o resultado real so
    sai depois de chamar a Apify. Usada so pro aviso de confirmacao do --yes."""
    estimated_results = (TAXA_REELS_POR_DIA + TAXA_POSTS_POR_DIA) * days * n_governors
    return round(estimated_results / 1000 * STARTER_PRICE_PER_1000_RESULTS, 2)


def estimate_cost_usd_for_results_limit(
    results_limit: int, n_governors: int, media_types: int = 2
) -> float:
    """Estimativa PRE-run para uma extracao sem janela de data (sem
    `onlyPostsNewerThan`, caso de um Recorte so com teto) --
    `results_limit` e um teto por perfil por tipo de midia aplicado pela
    Apify, entao o pior caso -- e o unico limite que da pra calcular sem
    rodar -- e cada perfil bater o teto em todos os tipos de midia
    chamados. `media_types` default 2 preserva o comportamento original
    (posts + reels); o UGC (ADR 0020, Ficha 8 / issue #93, via `src/coleta/custo.py`) chama com `media_types=1` -- um actor
    so (`apify/instagram-tagged-scraper`), nao dois."""
    worst_case_results = results_limit * media_types * n_governors
    return round(worst_case_results / 1000 * STARTER_PRICE_PER_1000_RESULTS, 2)


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
