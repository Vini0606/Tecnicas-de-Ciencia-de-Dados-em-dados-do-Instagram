"""Landing: o payload bruto da Apify, sem filtro do Recorte, em toda Coleta (ADR 0045).

Um arquivo por fonte em `landing/<run_id>/`, cada um uma lista JSON de itens exatamente como a Apify devolveu
(inclusive os registros de erro e os itens fora do Recorte, que a Bronze descarta). É a cópia fiel do que foi pago.
O formato é o da landing da Coleta do Reboot.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PASTA = "landing"
FONTES = ("profiles", "posts", "reels", "ugc_mentions")
# nome do arquivo na landing -> nome da fonte no manifesto
FONTE_NO_MANIFESTO = {"profiles": "perfis", "posts": "posts", "reels": "reels", "ugc_mentions": "ugc"}


class LandingInvalida(ValueError):
    """A pasta de landing não tem as quatro fontes em listas JSON."""


def pasta_da_landing(destino: Path | str, run_id: str) -> Path:
    return Path(destino) / PASTA / run_id


def gravar(destino: Path | str, run_id: str, fonte: str, itens: list[dict]) -> Path:
    """Grava os itens de uma fonte assim que o actor devolve (antes do filtro do Recorte e da Bronze)."""
    if fonte not in FONTES:
        raise ValueError(f"fonte de landing desconhecida: {fonte!r}")
    pasta = pasta_da_landing(destino, run_id)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{fonte}.json"
    arquivo.write_text(json.dumps(itens, ensure_ascii=False), encoding="utf-8")
    return arquivo


class ScraperComLanding:
    """Embrulha o scraper: cada actor que devolve itens tem o payload gravado na landing antes de qualquer filtro.
    Repassa os itens sem tocar neles; uma falha do actor passa direto e não grava nada daquela fonte."""

    def __init__(self, scraper, destino: Path | str, run_id: str):
        self._scraper = scraper
        self._destino = destino
        self._run_id = run_id

    @property
    def execucoes(self) -> list[dict]:
        return getattr(self._scraper, "execucoes", [])

    def scrape_profiles(self, links):
        return self._gravar("profiles", self._scraper.scrape_profiles(links))

    def scrape_posts(self, links, extra_run_input=None):
        return self._gravar("posts", self._scraper.scrape_posts(links, extra_run_input=extra_run_input))

    def scrape_reels(self, links, extra_run_input=None):
        return self._gravar("reels", self._scraper.scrape_reels(links, extra_run_input=extra_run_input))

    def scrape_mentions(self, links, extra_run_input=None):
        return self._gravar("ugc_mentions", self._scraper.scrape_mentions(links, extra_run_input=extra_run_input))

    def _gravar(self, fonte: str, itens: list[dict]) -> list[dict]:
        gravar(self._destino, self._run_id, fonte, itens)
        return itens


def _contar(arquivo: Path) -> int:
    try:
        itens = json.loads(arquivo.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erro:
        raise LandingInvalida(f"{arquivo.name}: JSON inválido ({erro.msg})") from None
    if not isinstance(itens, list):
        raise LandingInvalida(f"{arquivo.name}: esperado uma lista JSON de itens")
    return len(itens)


def resumo(destino: Path | str) -> dict[str, Any] | None:
    """Bloco `landing` do manifesto (`run_id` e, por fonte, `itens` e `bytes`), ou `None` se o Snapshot não tem landing.

    Levanta `LandingInvalida` se houver mais de um `run_id`, ou se faltar uma das quatro fontes (exceto a de UGC,
    que é tolerante a falha e pode não existir), ou se um arquivo não for uma lista JSON."""
    raiz = Path(destino) / PASTA
    runs = sorted(p for p in raiz.iterdir() if p.is_dir()) if raiz.is_dir() else []
    if not runs:
        return None
    if len(runs) > 1:
        raise LandingInvalida(f"a landing deve ter um único run_id; encontrados {[p.name for p in runs]}")
    run = runs[0]
    fontes: dict[str, dict[str, int]] = {}
    for fonte in FONTES:
        arquivo = run / f"{fonte}.json"
        if not arquivo.is_file():
            if fonte == "ugc_mentions":  # o UGC é tolerante a falha: pode não ter sido gravado
                continue
            raise LandingInvalida(f"falta {fonte}.json na landing de {run.name}")
        fontes[FONTE_NO_MANIFESTO[fonte]] = {"itens": _contar(arquivo), "bytes": arquivo.stat().st_size}
    return {"run_id": run.name, "fontes": fontes}
