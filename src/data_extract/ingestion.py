"""
Ponto único compartilhado de "raspar perfis+posts+reels e escrever na
Bronze" — usado por `pipeline.py`, `scripts/run_apify_backfill.py` e
`lambdas/extract/handler.py`, que antes duplicavam essa sequência sem
nenhum compartilhamento (ver ADR 0011, decisão 2).

Também responsável por arquivar o JSON bruto retornado pela Apify numa
landing zone, antes de qualquer projeção de schema acontecer (a Bronze
descarta silenciosamente campos fora do seu schema fixo — ver ADR 0011,
decisão 1). O arquivamento acontece sempre antes da escrita na Bronze para
cada entidade, então uma falha na escrita da Bronze não implica perda do
dado bruto já raspado (e já pago) da Apify.
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
    projeção de schema — fidelidade total, para não perder campos que a
    Bronze ainda não modela.

    Layout `<landing_dir>/<run_id>/<entity>.json` — pasta por `run_id`, não
    por entidade — para que arquivar/apagar tudo de uma execução seja uma
    operação de filesystem só (`rm -rf landing/<run_id>/`), sem precisar
    acertar uma pasta por entidade. Cruzar por `run_id` continua igual de
    fácil nos dois esquemas (é o nome da pasta em vez do nome do arquivo)."""
    run_dir = Path(landing_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{entity}.json"
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
    (ex: `onlyPostsNewerThan`) se aplica a posts/reels, não a perfis — o
    ator de perfis da Apify não aceita esse parâmetro. Retorna os itens
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
