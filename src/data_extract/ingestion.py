"""
Ponto único compartilhado de "raspar perfis+posts+reels+UGC e escrever na
Bronze" — usado por `pipeline.py`, `scripts/run_apify_backfill.py` e
`lambdas/extract/handler.py`, que antes duplicavam essa sequência sem
nenhum compartilhamento (ver ADR 0011, decisão 2).

A Bronze é fiel ao item da Apify (coluna `_raw` com o item completo, ADR 0039):
não existe mais landing zone separada, então uma falha na escrita da Bronze de
uma entidade não afeta as já gravadas.
"""

from __future__ import annotations

import logging

from src.data_extract.bronze_writer import BronzeWriter
from src.data_extract.scraper import InstagramScraper

logger = logging.getLogger(__name__)


def extract_and_land(
    scraper: InstagramScraper,
    bronze: BronzeWriter,
    links: list[str],
    run_id: str,
    extra_run_input: dict | None = None,
) -> dict[str, list[dict] | str]:
    """Raspa perfis+posts+reels+UGC, escreve na Bronze,
    nessa ordem, entidade por entidade. `extra_run_input`
    (ex: `onlyPostsNewerThan`) se aplica a posts/reels/UGC, não a perfis — o
    ator de perfis da Apify não aceita esse parâmetro. Retorna os itens
    brutos raspados por entidade.

    UGC (ADR 0020 Ficha 8, issue #211) é a ÚLTIMA coleta e é tolerante a
    falha: exceção do actor, lista vazia ou Bronze sem caminho de UGC viram
    `ugc_mentions == []` mais `ugc_error` no retorno, sem levantar --
    perfis/posts/reels já pagos e gravados nunca são descartados por ela.
    Perfis/posts/reels continuam fail-fast."""
    profiles = scraper.scrape_profiles(links)
    bronze.write_profiles(profiles, run_id=run_id)

    posts = scraper.scrape_posts(links, extra_run_input=extra_run_input)
    bronze.write_posts(posts, run_id=run_id)

    reels = scraper.scrape_reels(links, extra_run_input=extra_run_input)
    bronze.write_reels(reels, run_id=run_id)

    result: dict[str, list[dict] | str] = {"profiles": profiles, "posts": posts, "reels": reels, "ugc_mentions": []}
    try:
        mentions = scraper.scrape_mentions(links, extra_run_input=extra_run_input)
        if not mentions:
            raise ValueError("a coleta de UGC não retornou nenhum post")
        bronze.write_ugc_mentions(mentions, run_id=run_id)
        result["ugc_mentions"] = mentions
    except Exception as e:
        logger.exception("[BRONZE] Coleta de UGC pulada -- perfis/posts/reels preservados.")
        result["ugc_error"] = f"{type(e).__name__}: {e}"
    return result
