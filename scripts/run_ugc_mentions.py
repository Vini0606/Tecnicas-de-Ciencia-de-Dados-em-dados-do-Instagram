"""
Coleta de produção de UGC de criação (ADR 0020, Ficha 8 / issue #93):
`apify/instagram-tagged-scraper` -> Bronze -> Silver -> Gold, sob o mesmo
run_id. Piloto pequeno (scripts/run_apify_mentions_pilot.py) já confirmou os
nomes reais de campo do actor (2026-09-19) e corrigiu o contrato Delta
(src/schemas_delta.py) -- este script é a coleta de verdade, gravando na
Bronze de produção pela primeira vez.

Standalone de propósito, fora de pipeline.py/run_deterministic_modeling --
mesmo padrão de scripts/run_growth_metrics.py: UGC tem actor e cadência
próprios, não compete pelos mesmos dados/recursos da modelagem
determinística (ver "Implementation Decisions" da issue #93).

NAO roda no import -- só via `uv run python scripts/run_ugc_mentions.py
--yes`, disparado manualmente. Gera custo real na conta Apify.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apify_client import ApifyClient
from dotenv import load_dotenv

load_dotenv()

from config import settings
from scripts.apify_backfill_shared import (
    estimate_cost_usd_for_results_limit,
    load_links,
)
from src.data_extract.bronze_writer import BronzeWriter
from src.data_extract.ingestion import extract_and_land_ugc_mentions
from src.data_extract.scraper import InstagramScraper, ScraperConfig
from src.features.gold.ugc_mentions_aggregator import GovernorUGCAggregator
from src.features.silver.ugc_mention_cleaner import UGCMentionCleaner
from src.repositories.delta_repository import DeltaRepository
from src.run_id import build_run_id

# Piloto pequeno de propósito (issue #93: "resultsLimit baixo") -- mesmo
# default de scripts/run_apify_mentions_pilot.py. A coleta em volume maior
# é uma decisão futura, depois de observar estabilidade em produção.
DEFAULT_RESULTS_LIMIT = 5


def run(apify_api_token: str, results_limit: int, run_id: str | None = None) -> dict:
    run_id = build_run_id(run_id)
    links = load_links()
    n_governors = len(links)

    # Usernames reais (não URLs) para cruzar contra mentions/taggedUsers --
    # governor_engagement (Gold) já existe da modelagem determinística e tem
    # a coluna `username` confirmada, sem precisar parsear a URL.
    repo = DeltaRepository(gold_dir=settings.GOLD_DIR, silver_dir=settings.SILVER_DIR)
    governor_usernames = repo.load_profiles()["username"].dropna().tolist()

    print(f"[1/4] Rodando apify/instagram-tagged-scraper para {n_governors} governadores "
          f"(resultsLimit: {results_limit}, run_id: {run_id})...")

    scraper = InstagramScraper(
        client=ApifyClient(apify_api_token),
        config=ScraperConfig(results_limit=results_limit),
    )
    bronze = BronzeWriter(
        bronze_profiles_path=settings.BRONZE_PROFILES,
        bronze_posts_path=settings.BRONZE_POSTS,
        bronze_reels_path=settings.BRONZE_REELS,
        bronze_ugc_mentions_path=settings.BRONZE_UGC_MENTIONS,
    )
    mentions = extract_and_land_ugc_mentions(scraper, bronze, settings.LANDING_DIR, links, run_id=run_id)
    print(f"[2/4] Resultado bruto: {len(mentions)} posts de UGC. Escrito na Bronze de produção.")

    print("[3/4] Limpando (Silver) e agregando (Gold)...")
    df_bronze = bronze.get_latest_ugc_mentions()
    cleaner = UGCMentionCleaner()
    df_silver = cleaner.clean(df_bronze, run_id=run_id, governor_usernames=governor_usernames)
    cleaner.write(df_silver, settings.SILVER_UGC_MENTIONS)

    aggregator = GovernorUGCAggregator()
    df_gold = aggregator.enrich(df_silver, run_id=run_id)
    aggregator.write(df_gold, settings.GOLD_UGC_MENTIONS)

    n_correlacionados = int(df_gold["governor_username"].notna().sum())
    n_organico = int(df_gold["is_organic"].sum())
    print(
        f"[4/4] Gold gravada: {len(df_gold)} posts ({n_correlacionados} correlacionados a um "
        f"governador conhecido, {n_organico} orgânicos / {len(df_gold) - n_organico} publi paga)."
    )
    return {
        "run_id": run_id,
        "n_governors": n_governors,
        "raw_count": len(mentions),
        "n_correlacionados": n_correlacionados,
        "n_organico": n_organico,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Coleta de producao de UGC de criacao (ADR 0020, Ficha 8 / issue #93) -- "
            "apify/instagram-tagged-scraper -> Bronze -> Silver -> Gold. "
            "ATENCAO: gera custo real na conta Apify."
        )
    )
    parser.add_argument(
        "--results-limit",
        type=int,
        default=DEFAULT_RESULTS_LIMIT,
        help=f"resultsLimit por governador (default: {DEFAULT_RESULTS_LIMIT}).",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="run_id a usar para esta execucao (default: gerado automaticamente).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirma que voce quer disparar a coleta (custo real na Apify). Obrigatorio.",
    )
    args = parser.parse_args()

    if not args.yes:
        n_governors = len(load_links())
        estimated_cost = estimate_cost_usd_for_results_limit(
            args.results_limit, n_governors, media_types=1
        )
        print(
            f"[ABORTADO] Este script escreve na BRONZE DE PRODUCAO e gera custo "
            f"real na conta Apify (~${estimated_cost} estimado, pior caso, para "
            f"{n_governors} governadores x {args.results_limit} resultsLimit). "
            "Rode de novo com --yes para confirmar."
        )
        raise SystemExit(1)

    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        raise SystemExit("[ERRO] APIFY_API_TOKEN nao encontrado no ambiente/.env.")

    result = run(apify_api_token=token, results_limit=args.results_limit, run_id=args.run_id)
    # Sem emoji: o console padrao do Windows usa cp1252 e levanta
    # UnicodeEncodeError ao imprimi-los.
    print(f"[OK] Coleta de UGC concluida com run_id: {result['run_id']}")
