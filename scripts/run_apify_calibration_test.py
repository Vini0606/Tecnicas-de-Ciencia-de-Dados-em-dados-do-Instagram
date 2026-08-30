"""
Teste de calibracao Apify (ver handoff 2026-08-29): roda os scrapers de posts
e reels com `onlyPostsNewerThan: "90 days"` para os 27 governadores e compara
o volume real contra a extrapolacao feita a partir da amostra atual (30
posts/reels mais recentes por governador, que cobre so ~2-3 semanas e pode
estar refletindo um pico de atividade nao representativo).

NAO roda no import nem em nenhum outro script -- so via `python -m
scripts.run_apify_calibration_test` ou `uv run python
scripts/run_apify_calibration_test.py`, disparado manualmente. Gera custo
real na conta Apify (~$5-15 estimado para os 27 governadores em 90 dias).

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

import pandas as pd

from config import settings
from src.data_extract.scraper import InstagramScraper, ScraperConfig

WINDOW_DAYS = 90
ONLY_NEWER_THAN = "90 days"

# Baseline calculado na sessao de 2026-08-29 a partir da amostra atual (30
# itens mais recentes por governador) -- ver handoff. E o que este teste
# calibra/confirma ou corrige.
BASELINE_REELS_PER_DAY = 1.65
BASELINE_POSTS_PER_DAY = 2.60

# Plano Starter da Apify usado nas estimativas de custo do backfill.
STARTER_PRICE_PER_1000_RESULTS = 2.30

# resultsLimit alto o suficiente para nao truncar o volume real de 90 dias
# por governador (o default de producao, RESULTS_LIMIT=30, e "os 30 mais
# recentes", nao "todos desde a data X" -- aqui queremos o total real).
CALIBRATION_RESULTS_LIMIT = 1000

CALIBRATION_DIR = settings.DATA_DIR / "calibration"


def _load_links() -> list[str]:
    df_gov = pd.read_excel(settings.GOVERNADORES_FILE)
    df_gov.columns = df_gov.columns.str.strip()
    return list(df_gov[settings.LINK_COLUMN].str.strip().unique())


def _project_backfill_costs(total_results_90d: int, n_governors: int) -> dict[int, float]:
    """Extrapola o total de resultados calibrado (90 dias, N governadores)
    para janelas de 1-4 anos e converte em custo estimado no plano Starter."""
    daily_rate = total_results_90d / WINDOW_DAYS
    projections = {}
    for years in (1, 2, 3, 4):
        days = 365 * years
        total_results = daily_rate * days
        cost = total_results / 1000 * STARTER_PRICE_PER_1000_RESULTS
        projections[years] = round(cost, 2)
    return projections


def run(apify_api_token: str) -> dict:
    links = _load_links()
    n_governors = len(links)
    print(f"[1/3] Rodando scrapers para {n_governors} governadores "
          f"(onlyPostsNewerThan: '{ONLY_NEWER_THAN}')...")

    scraper = InstagramScraper(
        client=ApifyClient(apify_api_token),
        config=ScraperConfig(results_limit=CALIBRATION_RESULTS_LIMIT),
    )
    extra_run_input = {"onlyPostsNewerThan": ONLY_NEWER_THAN}

    posts = scraper.scrape_posts(links, extra_run_input=extra_run_input)
    reels = scraper.scrape_reels(links, extra_run_input=extra_run_input)

    print(f"[2/3] Resultado bruto: {len(posts)} posts, {len(reels)} reels.")

    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    posts_path = CALIBRATION_DIR / f"posts_90d_{stamp}.json"
    reels_path = CALIBRATION_DIR / f"reels_90d_{stamp}.json"
    posts_path.write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")
    reels_path.write_text(json.dumps(reels, ensure_ascii=False, indent=2), encoding="utf-8")

    actual_reels_per_day = len(reels) / WINDOW_DAYS / n_governors
    actual_posts_per_day = len(posts) / WINDOW_DAYS / n_governors

    print("[3/3] Comparando contra baseline extrapolado da amostra anterior...")
    report = {
        "n_governors": n_governors,
        "window_days": WINDOW_DAYS,
        "raw_counts": {"posts": len(posts), "reels": len(reels)},
        "rate_per_governor_per_day": {
            "reels": {"baseline": BASELINE_REELS_PER_DAY, "calibrated": round(actual_reels_per_day, 3)},
            "posts": {"baseline": BASELINE_POSTS_PER_DAY, "calibrated": round(actual_posts_per_day, 3)},
        },
        "backfill_cost_projection_usd_starter_plan": _project_backfill_costs(
            len(posts) + len(reels), n_governors
        ),
        "raw_data_paths": {"posts": str(posts_path), "reels": str(reels_path)},
    }

    report_path = CALIBRATION_DIR / f"calibration_report_{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[OK] Relatorio salvo em {report_path}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Teste de calibracao Apify (90 dias, 27 governadores). "
            "ATENCAO: gera custo real na conta Apify (~$5-15 estimado)."
        )
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirma que voce quer disparar o teste (custo real na Apify). Obrigatorio.",
    )
    args = parser.parse_args()

    if not args.yes:
        print(
            "[ABORTADO] Este script gera custo real na conta Apify (~$5-15 "
            "estimado). Rode de novo com --yes para confirmar."
        )
        raise SystemExit(1)

    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        raise SystemExit("[ERRO] APIFY_API_TOKEN nao encontrado no ambiente/.env.")

    run(apify_api_token=token)
    print("[OK] Teste de calibracao concluido.")
