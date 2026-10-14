"""Estimativa de custo (US$) de um Recorte nos quatro actors pagos (perfis, posts, reels, UGC).

Duas faixas (issue #294):

- **esperado**: posts e reels pela taxa diária calibrada (ADR 0012), limitada pelo teto por perfil de cada
  coleção; UGC sem calibração, então pelo teto cheio (conservador); perfis, um resultado por governador.
- **pior caso**: teto cheio em cada coleção.

Preços por actor e por plano da conta Apify, sem rede: a tabela abaixo é um retrato com data de verificação.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from config import settings
from scripts.apify_backfill_shared import (
    TAXA_POSTS_POR_DIA,
    TAXA_REELS_POR_DIA,
    default_results_limit,
)
from src.coleta.recorte import Recorte

if TYPE_CHECKING:
    from src.coleta.calibracao import Calibracao

PLANO_PADRAO = "BRONZE"  # equivale ao Starter (assumido; confirmar no Console da Apify)
PRECOS_VERIFICADOS_EM = "2026-10-13"

# US$ por 1.000 resultados, por plano. Fonte: api.apify.com/v2/acts/<slug>, `pricingInfos` mais recente
# (ver aba "Actors Apify" do dicionário de dados).
_PERFIS = {"FREE": 2.70, "BRONZE": 2.30, "SILVER": 1.90, "GOLD": 1.50, "PLATINUM": 0.90, "DIAMOND": 0.50}
_UGC = {"FREE": 2.70, "BRONZE": 2.30, "SILVER": 1.90, "GOLD": 1.50, "PLATINUM": 1.00, "DIAMOND": 0.50}
_REELS = {"FREE": 2.60, "BRONZE": 2.30, "SILVER": 1.40, "GOLD": 1.00, "PLATINUM": 0.80, "DIAMOND": 0.40}
# Posts: evento "post" + evento "post-details". Assume-se que os dois incidem em cada post (conservador;
# confirmar pelo faturamento da primeira Coleta de 90 dias).
_POSTS_BASE = {"FREE": 1.70, "BRONZE": 1.50, "SILVER": 1.30, "GOLD": 1.00, "PLATINUM": 0.80, "DIAMOND": 0.40}
_POSTS_DETALHES = {"FREE": 1.00, "BRONZE": 0.80, "SILVER": 0.70, "GOLD": 0.60, "PLATINUM": 0.20, "DIAMOND": 0.10}
PRECO_POR_1000: dict[str, dict[str, float]] = {
    "perfis": _PERFIS,
    "posts": {p: round(_POSTS_BASE[p] + _POSTS_DETALHES[p], 2) for p in _POSTS_BASE},
    "reels": _REELS,
    "ugc": _UGC,
}
REELS_ACTOR_START_USD = 0.001  # taxa fixa por execução do actor de reels


def teto_efetivo(recorte: Recorte, hoje: date) -> int:
    """Teto informado; senão, com janela, o padrão por janela do backfill;
    senão, o padrão do projeto."""
    if recorte.teto is not None:
        return recorte.teto
    dias = recorte.dias_a_extrair(hoje)
    return default_results_limit(dias) if dias else settings.RESULTS_LIMIT


COLECOES = ("perfis", "posts", "reels", "ugc")


def agregar_custo_real(execucoes: list[dict] | None) -> dict[str, float] | None:
    """Soma o custo real por coleção (um actor pode rodar mais de uma vez). Mesmas chaves de custo do
    estimado (`perfis`, `posts`, `reels`, `ugc`, `total`) mais `resultados_<coleção>`.

    Devolve `None` sem registro ou se qualquer chamada veio sem custo legível: nunca soma parcial."""
    if not execucoes or any(e.get("usd") is None for e in execucoes):
        return None
    custo = {c: 0.0 for c in COLECOES}
    itens = {c: 0 for c in COLECOES}
    for e in execucoes:
        custo[e["colecao"]] += e["usd"]
        itens[e["colecao"]] += e["itens"]
    real = {c: round(v, 4) for c, v in custo.items()}
    real["total"] = round(sum(custo.values()), 4)
    real.update({f"resultados_{c}": itens[c] for c in COLECOES})
    return real


def teto_e_padrao(recorte: Recorte) -> bool:
    """Verdadeiro quando o teto não foi informado e vale o padrão (sem `--teto`)."""
    return recorte.teto is None


def _precos(plano: str) -> dict[str, float]:
    plano = plano.upper()
    if plano not in _PERFIS:
        raise ValueError(f"plano Apify desconhecido: {plano!r}; use um de {sorted(_PERFIS)}")
    return {actor: tabela[plano] for actor, tabela in PRECO_POR_1000.items()}


def estimar_custo(
    recorte: Recorte,
    n_governadores: int,
    hoje: date,
    plano: str = PLANO_PADRAO,
    calibracao: Calibracao | None = None,
) -> dict[str, float]:
    """Dicionário plano (texto -> número, o formato que o manifesto grava).

    `posts_reels`, `ugc`, `perfis` e `total` são o **esperado**; `pior_caso_*` é o teto cheio por coleção;
    `resultados_*` são os resultados esperados por coleção. Com `calibracao` (issue #299), posts e reels usam a
    taxa de cada governador; sem ela, ou em fallback, as taxas fixas da ADR 0012. O pior caso não depende dela."""
    preco = _precos(plano)
    teto = teto_efetivo(recorte, hoje)
    dias = recorte.dias_a_extrair(hoje)

    def esperado(colecao: str, taxa_fixa: float) -> float:
        if not dias:
            return n_governadores * teto
        if calibracao is None or calibracao.usa_taxas_fixas:
            return n_governadores * min(taxa_fixa * dias, teto)
        # taxa de cada governador (Coleta anterior); quem não tem usa a média dos calibrados
        taxas = calibracao.taxas[colecao].values()
        sem_taxa = max(n_governadores - len(taxas), 0)
        return sum(min(r * dias, teto) for r in taxas) + sem_taxa * min(calibracao.taxa_media[colecao] * dias, teto)

    res_posts, res_reels = esperado("posts", TAXA_POSTS_POR_DIA), esperado("reels", TAXA_REELS_POR_DIA)
    res_teto_cheio = n_governadores * teto  # pior caso de cada coleção; também o UGC esperado (sem calibração)

    def usd(resultados: float, actor: str) -> float:
        return resultados / 1000 * preco[actor]

    perfis = usd(n_governadores, "perfis")
    ugc = usd(res_teto_cheio, "ugc")
    posts, reels = usd(res_posts, "posts"), usd(res_reels, "reels") + REELS_ACTOR_START_USD
    pior_posts = usd(res_teto_cheio, "posts")
    pior_reels = usd(res_teto_cheio, "reels") + REELS_ACTOR_START_USD

    return {
        "posts": round(posts, 2),
        "reels": round(reels, 2),
        "posts_reels": round(posts + reels, 2),
        "ugc": round(ugc, 2),
        "perfis": round(perfis, 2),
        "total": round(posts + reels + ugc + perfis, 2),
        "pior_caso_posts": round(pior_posts, 2),
        "pior_caso_reels": round(pior_reels, 2),
        "pior_caso_posts_reels": round(pior_posts + pior_reels, 2),
        "pior_caso_ugc": round(ugc, 2),
        "pior_caso_perfis": round(perfis, 2),
        "pior_caso_total": round(pior_posts + pior_reels + ugc + perfis, 2),
        "resultados_posts": res_posts,
        "resultados_reels": res_reels,
        "resultados_ugc": res_teto_cheio,
    }
