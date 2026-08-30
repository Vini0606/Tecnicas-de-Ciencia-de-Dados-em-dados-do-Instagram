"""
Backfill historico Apify: roda os scrapers de perfis/posts/reels com
`onlyPostsNewerThan` para os 27 governadores e escreve DIRETO NA BRONZE DE
PRODUCAO via `BronzeWriter` -- diferente de
`scripts/run_apify_calibration_test.py`, que e isolado em
`data/calibration/` e nunca toca a Bronze real.

So roda depois que a janela do backfill (1-4 anos) ja foi decidida com base
no teste de calibracao. --days e obrigatorio (sem default) para forcar uma
escolha explicita a cada execucao -- nao existe "janela segura" default pra
uma operacao que grava em producao.

So faz a extracao (profiles + posts + reels sob o mesmo run_id, igual ao
branch de extracao do `pipeline.py`) -- NAO roda Silver/Gold. Depois de
rodar este script, execute `uv run python pipeline.py` normalmente: ele
detecta a Bronze ja preenchida (`_bronze_has_data`) e cascateia Silver/Gold
a partir dela, sem reextrair.

NAO roda no import -- so via `uv run python scripts/run_apify_backfill.py
--days N --yes`, disparado manualmente. Gera custo real na conta Apify.
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apify_client import ApifyClient
from dotenv import load_dotenv

load_dotenv()

from config import settings
from scripts.apify_backfill_shared import (
    BASELINE_POSTS_PER_DAY,
    BASELINE_REELS_PER_DAY,
    RESULTS_LIMIT_FLOOR,
    RESULTS_LIMIT_SAFETY_MARGIN_PER_DAY,
    default_results_limit,
    estimate_cost_usd,
    load_links,
    profiles_hitting_limit,
    project_backfill_costs,
)
from src.data_extract.bronze_writer import BronzeWriter
from src.data_extract.scraper import InstagramScraper, ScraperConfig

BACKFILL_REPORT_DIR = settings.DATA_DIR / "backfill"


def run(apify_api_token: str, days: int, results_limit: int, run_id: str | None = None) -> dict:
    run_id = run_id or str(uuid.uuid4())
    links = load_links()
    n_governors = len(links)
    only_newer_than = f"{days} days"
    print(f"[1/3] Rodando scrapers para {n_governors} governadores "
          f"(onlyPostsNewerThan: '{only_newer_than}', resultsLimit: {results_limit}, "
          f"run_id: {run_id})...")

    scraper = InstagramScraper(
        client=ApifyClient(apify_api_token),
        config=ScraperConfig(results_limit=results_limit),
    )
    extra_run_input = {"onlyPostsNewerThan": only_newer_than}

    profiles = scraper.scrape_profiles(links)
    posts = scraper.scrape_posts(links, extra_run_input=extra_run_input)
    reels = scraper.scrape_reels(links, extra_run_input=extra_run_input)

    print(
        f"[2/3] Resultado bruto: {len(profiles)} profiles, {len(posts)} posts, "
        f"{len(reels)} reels. Escrevendo na Bronze de producao..."
    )
    truncated = {
        "posts": profiles_hitting_limit(posts, results_limit),
        "reels": profiles_hitting_limit(reels, results_limit),
    }
    if truncated["posts"] or truncated["reels"]:
        print(
            "[AVISO] resultsLimit provavelmente truncou o resultado real para "
            f"estes perfis (bateram exatamente no teto de {results_limit}): "
            f"posts={truncated['posts']} reels={truncated['reels']}. "
            "Rode de novo com --results-limit maior para esses casos."
        )

    bronze = BronzeWriter(
        bronze_profiles_path=settings.BRONZE_PROFILES,
        bronze_posts_path=settings.BRONZE_POSTS,
        bronze_reels_path=settings.BRONZE_REELS,
    )
    bronze.write_profiles(profiles, run_id=run_id)
    bronze.write_posts(posts, run_id=run_id)
    bronze.write_reels(reels, run_id=run_id)

    actual_reels_per_day = len(reels) / days / n_governors
    actual_posts_per_day = len(posts) / days / n_governors

    print("[3/3] Gerando relatorio do backfill...")
    report = {
        "run_id": run_id,
        "n_governors": n_governors,
        "window_days": days,
        "results_limit": results_limit,
        "raw_counts": {"profiles": len(profiles), "posts": len(posts), "reels": len(reels)},
        "rate_per_governor_per_day": {
            "reels": {"baseline": BASELINE_REELS_PER_DAY, "calibrated": round(actual_reels_per_day, 3)},
            "posts": {"baseline": BASELINE_POSTS_PER_DAY, "calibrated": round(actual_posts_per_day, 3)},
        },
        "backfill_cost_projection_usd_starter_plan": project_backfill_costs(
            len(posts) + len(reels), days
        ),
        "truncated_profiles": truncated,
    }

    BACKFILL_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = BACKFILL_REPORT_DIR / f"backfill_report_{days}d_{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[OK] Relatorio salvo em {report_path}")
    print(
        "[PROXIMO PASSO] Rode 'uv run python pipeline.py' para cascatear "
        "Silver/Gold a partir da Bronze recem-preenchida (ele detecta os "
        "dados novos e nao reextrai)."
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Backfill historico Apify -- escreve na Bronze DE PRODUCAO. "
            "ATENCAO: gera custo real na conta Apify -- veja a estimativa "
            "antes de confirmar com --yes."
        )
    )
    parser.add_argument(
        "--days",
        type=int,
        required=True,
        help="Janela em dias para onlyPostsNewerThan. Obrigatorio -- sem default seguro para producao.",
    )
    parser.add_argument(
        "--results-limit",
        type=int,
        default=None,
        help=(
            "resultsLimit por run, por perfil (default: escala com --days, "
            f"max({RESULTS_LIMIT_FLOOR}, days * {RESULTS_LIMIT_SAFETY_MARGIN_PER_DAY}))."
        ),
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="run_id a usar para esta extracao (default: gerado automaticamente).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirma que voce quer disparar o backfill (custo real na Apify, escreve em producao). Obrigatorio.",
    )
    args = parser.parse_args()
    results_limit = args.results_limit or default_results_limit(args.days)

    if not args.yes:
        n_governors = len(load_links())
        estimated_cost = estimate_cost_usd(args.days, n_governors)
        print(
            f"[ABORTADO] Este script escreve na BRONZE DE PRODUCAO e gera custo "
            f"real na conta Apify (~${estimated_cost} estimado para {args.days} "
            f"dias, {n_governors} governadores, baseado no baseline conhecido -- "
            "o custo real pode variar). Rode de novo com --yes para confirmar."
        )
        raise SystemExit(1)

    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        raise SystemExit("[ERRO] APIFY_API_TOKEN nao encontrado no ambiente/.env.")

    run(apify_api_token=token, days=args.days, results_limit=results_limit, run_id=args.run_id)
    print("[OK] Backfill concluido.")
