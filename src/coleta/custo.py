"""Estimativa de custo (US$) de um Recorte nos quatro actors pagos (perfis, posts, reels, UGC).

Três números por coleção (ADR 0042), todos em US$ e em itens:

- **estimado**: média + 3 desvios-padrão do total, projetada da Base de calibração (a Coleta anterior, por menor que
  seja a janela dela) para o novo Recorte; nunca acima do máximo. Sem base vale o máximo.
- **máximo**: o Teto aplicado cheio em todos os perfis, o único valor garantido.
- **resultados**: os itens por trás do estimado.

Preços por actor e por plano da conta Apify, sem rede: a tabela abaixo é um retrato com data de verificação.
"""

from __future__ import annotations

import math
import statistics
from datetime import date
from typing import TYPE_CHECKING

from config import settings
from scripts.apify_backfill_shared import default_results_limit
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
# Posts: evento "post" + evento "post-details", cobrados nos dois em cada post (confirmado nos 4 runs reais do piloto).
_POSTS_BASE = {"FREE": 1.70, "BRONZE": 1.50, "SILVER": 1.30, "GOLD": 1.00, "PLATINUM": 0.80, "DIAMOND": 0.40}
_POSTS_DETALHES = {"FREE": 1.00, "BRONZE": 0.80, "SILVER": 0.70, "GOLD": 0.60, "PLATINUM": 0.20, "DIAMOND": 0.10}
PRECO_POR_1000: dict[str, dict[str, float]] = {
    "perfis": _PERFIS,
    "posts": {p: round(_POSTS_BASE[p] + _POSTS_DETALHES[p], 2) for p in _POSTS_BASE},
    "reels": _REELS,
    "ugc": _UGC,
}
REELS_ACTOR_START_USD = 0.001  # taxa fixa por execução do actor de reels

COLECOES = ("perfis", "posts", "reels", "ugc")
COLECOES_CALIBRADAS = ("posts", "reels", "ugc")
COLECOES_POR_JANELA = ("posts", "reels")  # o UGC não depende da janela, só do teto
SEM_BASE = "sem_base"
SIGMAS = 3  # desvios-padrão somados à média do total


def teto_efetivo(recorte: Recorte, hoje: date) -> int:
    """Teto informado; senão, com janela, o padrão por janela (`max(200, 7 × dias)`);
    senão, o padrão do projeto."""
    if recorte.teto is not None:
        return recorte.teto
    dias = recorte.dias_a_extrair(hoje)
    return default_results_limit(dias) if dias else settings.RESULTS_LIMIT


def teto_e_padrao(recorte: Recorte) -> bool:
    """Verdadeiro quando o teto não foi informado e vale o padrão (sem `--teto`)."""
    return recorte.teto is None


def agregar_custo_real(execucoes: list[dict] | None) -> dict[str, dict[str, float]] | None:
    """Soma o custo real por coleção (um actor pode rodar mais de uma vez), no formato do bloco `real` do manifesto:
    `custo_usd` e `resultados_itens`, cada um com `perfis`, `posts`, `reels`, `ugc` e `total`.

    Devolve `None` sem registro ou se qualquer chamada veio sem custo legível: nunca soma parcial."""
    if not execucoes or any(e.get("usd") is None for e in execucoes):
        return None
    custo = {c: 0.0 for c in COLECOES}
    itens = {c: 0 for c in COLECOES}
    for e in execucoes:
        custo[e["colecao"]] += e["usd"]
        itens[e["colecao"]] += e["itens"]
    usd = {c: round(v, 4) for c, v in custo.items()}
    usd["total"] = round(sum(custo.values()), 4)
    return {"custo_usd": usd, "resultados_itens": {**itens, "total": sum(itens.values())}}


def diferenca_percentual(estimado: dict, real: dict | None) -> dict[str, dict[str, float]] | None:
    """Bloco `diferenca` do manifesto: `(real − estimado) / estimado × 100`, só percentual, por coleção e no total.
    Negativo = gastou menos que o estimado (folga). `None` se não há custo real."""
    if real is None:
        return None
    pares = {"custo_pct": ("estimado_usd", "custo_usd"), "resultados_pct": ("resultados_itens", "resultados_itens")}
    diferenca: dict[str, dict[str, float]] = {}
    for nome, (chave_est, chave_real) in pares.items():
        diferenca[nome] = {
            c: round((real[chave_real][c] - estimado[chave_est][c]) / estimado[chave_est][c] * 100, 1)
            for c in (*COLECOES, "total")
        }
    return diferenca


def _precos(plano: str) -> dict[str, float]:
    plano = plano.upper()
    if plano not in _PERFIS:
        raise ValueError(f"plano Apify desconhecido: {plano!r}; use um de {sorted(_PERFIS)}")
    return {actor: tabela[plano] for actor, tabela in PRECO_POR_1000.items()}


def _projetar(
    colecao: str, n_governadores: int, teto: int, dias: int | None, calibracao: Calibracao | None
) -> tuple[int, str]:
    """Itens estimados de uma coleção e a Base de calibração usada (`sem_base` = vale o máximo).

    Cada governador da base é projetado para o novo Recorte: posts e reels pela taxa diária × dias, UGC pela contagem
    (independe da janela), ambos limitados ao novo teto; quem bateu o teto da base está censurado e sobe ao novo teto.
    Governador novo (o elenco cresceu desde a base) entra com a média; os demais ausentes da base não tiveram itens.
    O total estimado é a soma + 3·√N·σ (σ entre os governadores), limitado ao máximo."""
    maximo = n_governadores * teto
    if calibracao is None or calibracao.usa_sem_base:
        return maximo, SEM_BASE
    contagens = calibracao.contagens.get(colecao) or {}
    por_janela = colecao in COLECOES_POR_JANELA
    if not contagens or (por_janela and (not dias or not calibracao.dias_janela)):
        return maximo, SEM_BASE

    def projetar(itens: int) -> float:
        if itens >= calibracao.base_teto:
            return float(teto)
        return min(itens / calibracao.dias_janela * dias, teto) if por_janela else float(min(itens, teto))

    valores = [projetar(itens) for itens in contagens.values()]  # governadores do elenco que aparecem na base
    ausentes = max(n_governadores - len(valores), 0)
    novos = min(max(n_governadores - calibracao.n_perfis_base, 0), ausentes)  # elenco que cresceu desde a base
    valores += [0.0] * (ausentes - novos)  # estavam na base e não tiveram itens
    valores += [statistics.mean(valores) if valores else 0.0] * novos
    sigma = statistics.pstdev(valores) if len(valores) > 1 else 0.0
    estimado = min(sum(valores) + SIGMAS * math.sqrt(n_governadores) * sigma, maximo)
    if estimado <= 0:  # base zerada nesta coleção: não prevê nada, vale o máximo
        return maximo, SEM_BASE
    return math.ceil(estimado), calibracao.origem or SEM_BASE


def estimar_custo(
    recorte: Recorte,
    n_governadores: int,
    hoje: date,
    plano: str = PLANO_PADRAO,
    calibracao: Calibracao | None = None,
) -> dict:
    """Bloco `estimado` do manifesto (ADR 0042): `estimado_usd`, `maximo_usd` e `resultados_itens` (cada um com
    `perfis`, `posts`, `reels`, `ugc` e `total`), `teto` (`aplicado_itens_por_perfil`, `padrao`) e `base_calibracao`
    (a Coleta que calibrou posts, reels e UGC, ou `sem_base`)."""
    preco = _precos(plano)
    teto = teto_efetivo(recorte, hoje)
    dias = recorte.dias_a_extrair(hoje)

    def usd(itens: float, colecao: str) -> float:
        extra = REELS_ACTOR_START_USD if colecao == "reels" else 0.0
        return itens / 1000 * preco[colecao] + extra

    itens: dict[str, int] = {"perfis": n_governadores}
    base: dict[str, str] = {}
    for colecao in COLECOES_CALIBRADAS:
        itens[colecao], base[colecao] = _projetar(colecao, n_governadores, teto, dias, calibracao)
    cheio = {c: (n_governadores if c == "perfis" else n_governadores * teto) for c in COLECOES}

    estimado_usd = {c: round(usd(itens[c], c), 4) for c in COLECOES}
    maximo_usd = {c: round(usd(cheio[c], c), 4) for c in COLECOES}
    estimado_usd["total"] = round(sum(estimado_usd.values()), 4)
    maximo_usd["total"] = round(sum(maximo_usd.values()), 4)
    return {
        "estimado_usd": estimado_usd,
        "maximo_usd": maximo_usd,
        "resultados_itens": {**itens, "total": sum(itens.values())},
        "teto": {"aplicado_itens_por_perfil": teto, "padrao": teto_e_padrao(recorte)},
        "base_calibracao": base,
    }
