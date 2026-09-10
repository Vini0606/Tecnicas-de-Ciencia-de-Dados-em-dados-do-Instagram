"""
Piloto do actor de UGC de criação (ADR 0020, Ficha 8 / issue #93):
`apify/instagram-tagged-scraper`, com `resultsLimit` baixo nos 27 perfis.

A issue #93 exige rodar este piloto ANTES de comprometer o contrato Delta em
`src/schemas_delta.py` (`BRONZE_UGC_MENTIONS_SCHEMA`) -- os nomes exatos de
campo do actor escolhido não têm exemplo de output confirmado para os
perfis reais do projeto (ver `docs/research/apify-instagram-actors-cobra-mapping.md`,
§7.1: só um exemplo isolado, de outro perfil, foi confirmado). O pipeline
completo (Bronze/Silver/Gold) já foi construído nesta issue com o contrato
atual, mas TODOS os campos além de `id`/`shortCode` estão `nullable=True`
exatamente para não quebrar quando este piloto rodar de verdade e revelar
nomes de campo diferentes.

ESTE SCRIPT NÃO FOI EXECUTADO nesta sessão de implementação -- não há
`APIFY_API_TOKEN` no ambiente do agente, e a chamada real gera custo na
conta Apify (fora do escopo de uma execução autônoma sem confirmação
humana). Precisa ser rodado manualmente por quem tem a credencial, com
`--yes`, antes de considerar a Ficha 8 validada em produção -- ver
"Verificação manual do piloto" nas Testing Decisions da issue #93.

NAO roda no import -- só via `python -m scripts.run_apify_mentions_pilot` ou
`uv run python scripts/run_apify_mentions_pilot.py`, disparado manualmente e
com --yes. Resultados brutos vão para `data/pilot/`, fora do Delta lake
(mesmo padrão de `scripts/run_apify_calibration_test.py`), para inspecionar
os campos reais antes de qualquer escrita em Bronze de produção.
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
from scripts.apify_backfill_shared import estimate_cost_usd_for_results_limit, load_links
from src.data_extract.scraper import InstagramScraper, ScraperConfig

PILOT_DIR = settings.DATA_DIR / "pilot"

# Piloto pequeno de propósito (issue #93: "resultsLimit baixo") -- o objetivo
# é confirmar nomes de campo e volume real, não coletar em escala ainda.
DEFAULT_RESULTS_LIMIT = 5


def run(apify_api_token: str, results_limit: int) -> dict:
    links = load_links()
    n_governors = len(links)
    print(
        f"[1/3] Rodando apify/instagram-tagged-scraper para {n_governors} "
        f"governadores (resultsLimit: {results_limit})..."
    )

    scraper = InstagramScraper(
        client=ApifyClient(apify_api_token),
        config=ScraperConfig(results_limit=results_limit),
    )
    items = scraper.scrape_mentions(links)

    print(f"[2/3] Resultado bruto: {len(items)} posts de UGC (tagged/mentioned).")

    PILOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = PILOT_DIR / f"mentions_pilot_{stamp}.json"
    raw_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[3/3] Confirmando nomes de campo e taxa de preenchimento reais...")
    field_presence = _field_presence(items)

    report = {
        "n_governors": n_governors,
        "results_limit": results_limit,
        "raw_count": len(items),
        "avg_items_per_governor": round(len(items) / n_governors, 3) if n_governors else 0,
        # Campos que a issue #93 espera coletar -- conferir manualmente
        # contra `field_presence` abaixo se os nomes batem antes de ajustar
        # `nullable=False`/nomes em `BRONZE_UGC_MENTIONS_SCHEMA`.
        "expected_fields": [
            "id",
            "shortCode",
            "caption",
            "mentions",
            "matchTypes",
            "likesCount",
            "commentsCount",
            "videoPlayCount",
            "authorUsername",
            "ownerUsername",
            "authorIsVerified",
            "isPaidPartnership",
            "isAd",
            "isAffiliate",
            "timestamp",
        ],
        "field_presence_pct": field_presence,
        "raw_data_path": str(raw_path),
    }

    report_path = PILOT_DIR / f"pilot_report_{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[OK] Relatorio salvo em {report_path}")
    return report


def _field_presence(items: list[dict]) -> dict:
    """% de itens que preenchem cada campo visto no dataset -- não presume
    nomes, lista o que o actor de fato retornou."""
    if not items:
        return {}
    counts: dict[str, int] = {}
    for item in items:
        for key, value in item.items():
            if value not in (None, "", []):
                counts[key] = counts.get(key, 0) + 1
    return {key: round(count / len(items) * 100, 1) for key, count in sorted(counts.items())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Piloto do apify/instagram-tagged-scraper (ADR 0020, Ficha 8 / "
            "issue #93). ATENCAO: gera custo real na conta Apify."
        )
    )
    parser.add_argument(
        "--results-limit",
        type=int,
        default=DEFAULT_RESULTS_LIMIT,
        help=f"resultsLimit por perfil (default: {DEFAULT_RESULTS_LIMIT}, piloto pequeno).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirma que voce quer disparar o piloto (custo real na Apify). Obrigatorio.",
    )
    args = parser.parse_args()

    if not args.yes:
        n_governors = len(load_links())
        # media_types=1: um actor so (apify/instagram-tagged-scraper), ao
        # contrario do default=2 (posts+reels) do resto do pipeline.
        estimated_cost = estimate_cost_usd_for_results_limit(
            args.results_limit, n_governors, media_types=1
        )
        print(
            f"[ABORTADO] Este script gera custo real na conta Apify (~${estimated_cost} "
            f"estimado, pior caso, para {n_governors} governadores x "
            f"{args.results_limit} resultsLimit). Rode de novo com --yes para confirmar."
        )
        raise SystemExit(1)

    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        raise SystemExit("[ERRO] APIFY_API_TOKEN nao encontrado no ambiente/.env.")

    run(apify_api_token=token, results_limit=args.results_limit)
    print("[OK] Piloto concluido. Confirme os nomes de campo antes de fixar o schema.")
