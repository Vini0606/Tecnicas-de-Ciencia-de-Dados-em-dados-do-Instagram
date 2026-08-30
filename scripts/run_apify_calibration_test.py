"""
Teste de calibracao Apify (ver handoff 2026-08-29): roda os scrapers de posts
e reels com `onlyPostsNewerThan` para os 27 governadores e compara o volume
real contra a extrapolacao feita a partir da amostra atual (30 posts/reels
mais recentes por governador, que cobre so ~2-3 semanas e pode estar
refletindo um pico de atividade nao representativo).

Janela (--days) e limite por perfil (--results-limit) sao parametrizaveis
via CLI -- o default (90 dias) e o teste de calibracao barato. Constantes e
formulas de custo/limite ficam em `scripts/apify_backfill_shared.py`, compartilhadas
com `scripts/run_apify_backfill.py` (o script que roda o backfill de
verdade, escrevendo na Bronze de producao -- ver esse arquivo).

NAO roda no import nem em nenhum outro script -- so via `python -m
scripts.run_apify_calibration_test` ou `uv run python
scripts/run_apify_calibration_test.py`, disparado manualmente e com --yes.
Gera custo real na conta Apify.

Nao usa o pipeline Medallion (Bronze/Silver/Gold) -- e um teste isolado, os
resultados brutos vao para `data/calibration/`, fora do Delta lake, para nao
misturar com dados de producao.
"""

import argparse
import json
import os
import sys
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
    DEFAULT_DAYS,
    RESULTS_LIMIT_FLOOR,
    RESULTS_LIMIT_SAFETY_MARGIN_PER_DAY,
    default_results_limit,
    estimate_cost_usd,
    load_links,
    profiles_hitting_limit,
    project_backfill_costs,
)
from src.data_extract.scraper import InstagramScraper, ScraperConfig

CALIBRATION_DIR = settings.DATA_DIR / "calibration"


def run(apify_api_token: str, days: int, results_limit: int) -> dict:
    links = load_links()
    n_governors = len(links)
    only_newer_than = f"{days} days"
    print(f"[1/3] Rodando scrapers para {n_governors} governadores "
          f"(onlyPostsNewerThan: '{only_newer_than}', resultsLimit: {results_limit})...")

    scraper = InstagramScraper(
        client=ApifyClient(apify_api_token),
        config=ScraperConfig(results_limit=results_limit),
    )
    extra_run_input = {"onlyPostsNewerThan": only_newer_than}

    posts = scraper.scrape_posts(links, extra_run_input=extra_run_input)
    reels = scraper.scrape_reels(links, extra_run_input=extra_run_input)

    print(f"[2/3] Resultado bruto: {len(posts)} posts, {len(reels)} reels.")
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

    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    posts_path = CALIBRATION_DIR / f"posts_{days}d_{stamp}.json"
    reels_path = CALIBRATION_DIR / f"reels_{days}d_{stamp}.json"
    posts_path.write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")
    reels_path.write_text(json.dumps(reels, ensure_ascii=False, indent=2), encoding="utf-8")

    actual_reels_per_day = len(reels) / days / n_governors
    actual_posts_per_day = len(posts) / days / n_governors

    print("[3/3] Comparando contra baseline extrapolado da amostra anterior...")
    report = {
        "n_governors": n_governors,
        "window_days": days,
        "results_limit": results_limit,
        "raw_counts": {"posts": len(posts), "reels": len(reels)},
        "rate_per_governor_per_day": {
            "reels": {"baseline": BASELINE_REELS_PER_DAY, "calibrated": round(actual_reels_per_day, 3)},
            "posts": {"baseline": BASELINE_POSTS_PER_DAY, "calibrated": round(actual_posts_per_day, 3)},
        },
        "backfill_cost_projection_usd_starter_plan": project_backfill_costs(
            len(posts) + len(reels), days
        ),
        "truncated_profiles": truncated,
        "raw_data_paths": {"posts": str(posts_path), "reels": str(reels_path)},
    }

    report_path = CALIBRATION_DIR / f"calibration_report_{days}d_{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[OK] Relatorio salvo em {report_path}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Teste de calibracao Apify. ATENCAO: gera custo real "
            "na conta Apify -- veja a estimativa antes de confirmar com --yes."
        )
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"Janela em dias para onlyPostsNewerThan (default: {DEFAULT_DAYS}).",
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
        "--yes",
        action="store_true",
        help="Confirma que voce quer disparar o teste (custo real na Apify). Obrigatorio.",
    )
    args = parser.parse_args()
    results_limit = args.results_limit or default_results_limit(args.days)

    if not args.yes:
        n_governors = len(load_links())
        estimated_cost = estimate_cost_usd(args.days, n_governors)
        print(
            f"[ABORTADO] Este script gera custo real na conta Apify (~${estimated_cost} "
            f"estimado para {args.days} dias, {n_governors} governadores, baseado no "
            "baseline conhecido -- o custo real pode variar). Rode de novo com --yes "
            "para confirmar."
        )
        raise SystemExit(1)

    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        raise SystemExit("[ERRO] APIFY_API_TOKEN nao encontrado no ambiente/.env.")

    run(apify_api_token=token, days=args.days, results_limit=results_limit)
    print("[OK] Teste de calibracao concluido.")
