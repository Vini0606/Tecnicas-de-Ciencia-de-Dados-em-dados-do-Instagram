"""
`coletar`: do Recorte ao Snapshot local (ADR 0039, issue #248).

Interface única da Coleta. Dado um Recorte, uma pasta de dados limpa
(`destino`) e um scraper da Apify (injetado), extrai perfis, posts, reels e
UGC, grava a Bronze fiel, deriva Silver e Gold na ordem e escreve o manifesto.
Sem rede própria: tudo que é externo (Apify, relógio, confirmação de custo)
entra por argumento, então os testes passam por aqui sem custo.

O `destino` segue o layout de `config.settings` (`bronze/instagram_*`,
`silver/*_clean`, `gold/governor_*`), o mesmo que o dashboard e a modelagem
leem. A derivação Silver/Gold mora em `src.coleta.derivacao` (compartilhada
com a Lambda de reconstrução, issue #253).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from scripts.apify_backfill_shared import profiles_hitting_limit
from src.coleta.custo import estimar_custo, teto_efetivo
from src.coleta.derivacao import caminhos_do_destino, derivar_silver_gold
from src.coleta.manifesto import escrever_manifesto, gerar_manifesto, versao_do_codigo
from src.coleta.recorte import Recorte, gerar_tag
from src.data_extract.bronze_writer import BronzeWriter
from src.data_extract.ingestion import extract_and_land
from src.data_extract.scraper import InstagramScraper, ScraperConfig
from src.features.silver.governors_metadata_cleaner import GovernorsMetadataCleaner
from src.run_id import build_run_id

logger = logging.getLogger(__name__)


class ColetaNaoConfirmada(Exception):
    """O custo estimado não foi confirmado: nenhuma chamada paga foi feita."""


@dataclass(frozen=True)
class ResultadoColeta:
    tag: str
    run_id: str
    destino: Path
    custo_estimado: dict[str, float]
    manifesto: dict


def criar_scraper(client, recorte: Recorte, hoje: date) -> InstagramScraper:
    """Scraper com o teto efetivo do Recorte -- o ponto único que traduz teto
    em `resultsLimit` da Apify."""
    return InstagramScraper(
        client=client, config=ScraperConfig(results_limit=teto_efetivo(recorte, hoje))
    )


class _ScraperRecortado:
    """Aplica localmente o intervalo absoluto do Recorte (a Apify só sabe
    'mais novo que X'). Sem intervalo, repassa tudo sem tocar nos itens."""

    def __init__(self, scraper, recorte: Recorte):
        self._scraper = scraper
        self._recorte = recorte

    def scrape_profiles(self, links):
        return self._scraper.scrape_profiles(links)

    def scrape_posts(self, links, extra_run_input=None):
        return self._filtrar(self._scraper.scrape_posts(links, extra_run_input=extra_run_input))

    def scrape_reels(self, links, extra_run_input=None):
        return self._filtrar(self._scraper.scrape_reels(links, extra_run_input=extra_run_input))

    def scrape_mentions(self, links, extra_run_input=None):
        return self._filtrar(self._scraper.scrape_mentions(links, extra_run_input=extra_run_input))

    def _filtrar(self, itens: list[dict]) -> list[dict]:
        if self._recorte.inicio is None:
            return itens
        return [i for i in itens if self._dentro(i)]

    def _dentro(self, item: dict) -> bool:
        publicado = pd.to_datetime(item.get("timestamp"), errors="coerce", utc=True)
        if pd.isna(publicado):
            return True  # sem data legível: não descarta o que não dá para avaliar
        return self._recorte.dentro_do_recorte(publicado.date())


def _avisar_truncados(bruto: dict, teto: int) -> None:
    """Perfis que bateram exatamente no teto: o resultado provavelmente foi truncado."""
    truncados = {
        entidade: profiles_hitting_limit(bruto.get(entidade, []), teto)
        for entidade in ("posts", "reels", "ugc_mentions")
    }
    if any(truncados.values()):
        logger.warning(
            "[COLETA] Perfis que bateram no teto de %s (resultado provavelmente truncado): "
            "posts=%s reels=%s ugc_mentions=%s. Rode de novo com --teto maior.",
            teto, truncados["posts"], truncados["reels"], truncados["ugc_mentions"],
        )


def coletar(
    recorte: Recorte,
    destino: Path | str,
    *,
    scraper,
    links: list[str],
    governor_usernames: list[str],
    df_governadores: pd.DataFrame,
    confirmar: Callable[[float], bool],
    hoje: date | None = None,
    agora: datetime | None = None,
    rotulo: str | None = None,
    run_id: str | None = None,
    modelar: Callable[[dict[str, pd.DataFrame]], None] | None = None,
) -> ResultadoColeta:
    """Executa uma Coleta completa em `destino` e devolve o Snapshot local.

    `confirmar(custo)` é chamado com o custo estimado (pior caso, US$) antes
    de qualquer chamada paga; se devolver falso, levanta `ColetaNaoConfirmada`
    sem tocar na Apify nem no disco. `modelar`, opcional, recebe as tabelas
    Silver/Gold já derivadas para a modelagem pesada (fora do escopo daqui)."""
    agora = agora or datetime.now(timezone.utc)
    hoje = hoje or agora.date()
    destino = Path(destino)
    run_id = build_run_id(run_id)

    custo = estimar_custo(recorte, len(links), hoje)
    if not confirmar(custo["total"]):
        raise ColetaNaoConfirmada(f"Custo estimado de US$ {custo['total']:.2f} não confirmado.")

    tag = gerar_tag(recorte, hoje, rotulo)
    p = caminhos_do_destino(destino)

    bronze = BronzeWriter(
        bronze_profiles_path=p["bronze_profiles"],
        bronze_posts_path=p["bronze_posts"],
        bronze_reels_path=p["bronze_reels"],
        bronze_ugc_mentions_path=p["bronze_ugc"],
    )
    dias = recorte.dias_a_extrair(hoje)
    extra = {"onlyPostsNewerThan": f"{dias} days"} if dias else None
    logger.info("[COLETA] %s: extraindo (custo estimado US$ %.2f)...", tag, custo["total"])
    bruto = extract_and_land(
        _ScraperRecortado(scraper, recorte), bronze, links, run_id=run_id, extra_run_input=extra
    )
    _avisar_truncados(bruto, teto_efetivo(recorte, hoje))

    governors_cleaner = GovernorsMetadataCleaner()
    governors_cleaner.write(governors_cleaner.clean(df_governadores, run_id), p["silver_governors"])

    derivar_silver_gold(bronze, p, governor_usernames, run_id, modelar=modelar)

    manifesto = gerar_manifesto(
        destino,
        tag=tag,
        recorte=recorte,
        extraido_em=agora,
        versao_codigo=versao_do_codigo(),
        custo_estimado=custo,
    )
    escrever_manifesto(destino, manifesto)
    return ResultadoColeta(
        tag=tag, run_id=run_id, destino=destino, custo_estimado=custo, manifesto=manifesto
    )
