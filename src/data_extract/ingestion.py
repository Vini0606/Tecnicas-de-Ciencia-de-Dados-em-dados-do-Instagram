"""
Ponto unico compartilhado de "raspar perfis+posts+reels e escrever na
Bronze" -- usado por `pipeline.py`, `scripts/run_apify_backfill.py` e
`lambdas/extract/handler.py`, que antes duplicavam essa sequencia sem
nenhum compartilhamento (ver ADR 0011, decisao 2).

Tambem responsavel por arquivar o JSON bruto retornado pela Apify numa
landing zone, antes de qualquer projecao de schema acontecer (a Bronze
descarta silenciosamente campos fora do seu schema fixo -- ver ADR 0011,
decisao 1). O arquivamento acontece sempre antes da escrita na Bronze para
cada entidade, entao uma falha na escrita da Bronze nao implica perda do
dado bruto ja raspado (e ja pago) da Apify.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.data_extract.bronze_writer import BronzeWriter
from src.data_extract.scraper import InstagramScraper


def archive_raw_json(
    landing_dir: Path | str, entity: str, raw_data: list[dict], run_id: str
) -> Path:
    """Grava a lista de itens brutos como veio da Apify, sem nenhuma
    projecao de schema -- fidelidade total, para nao perder campos que a
    Bronze ainda nao modela."""
    entity_dir = Path(landing_dir) / entity
    entity_dir.mkdir(parents=True, exist_ok=True)
    path = entity_dir / f"{run_id}.json"
    path.write_text(json.dumps(raw_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def extract_and_land(
    scraper: InstagramScraper,
    bronze: BronzeWriter,
    landing_dir: Path | str,
    links: list[str],
    run_id: str,
    extra_run_input: dict | None = None,
) -> dict[str, list[dict]]:
    """Raspa perfis+posts+reels, arquiva cada entidade na landing zone e
    escreve na Bronze, nessa ordem, entidade por entidade. `extra_run_input`
    (ex: `onlyPostsNewerThan`) se aplica a posts/reels, nao a perfis -- o
    ator de perfis da Apify nao aceita esse parametro. Retorna os itens
    brutos raspados por entidade."""
    profiles = scraper.scrape_profiles(links)
    archive_raw_json(landing_dir, "profiles", profiles, run_id)
    bronze.write_profiles(profiles, run_id=run_id)

    posts = scraper.scrape_posts(links, extra_run_input=extra_run_input)
    archive_raw_json(landing_dir, "posts", posts, run_id)
    bronze.write_posts(posts, run_id=run_id)

    reels = scraper.scrape_reels(links, extra_run_input=extra_run_input)
    archive_raw_json(landing_dir, "reels", reels, run_id)
    bronze.write_reels(reels, run_id=run_id)

    return {"profiles": profiles, "posts": posts, "reels": reels}
