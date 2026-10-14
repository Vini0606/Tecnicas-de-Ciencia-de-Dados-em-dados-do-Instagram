"""Calibração por perfil da estimativa de custo com a Coleta vigente no HF (issue #299).

A taxa de cada governador é `itens / dias da janela` da Coleta anterior (cobertura por perfil do
manifesto). Quando essa Coleta não serve (janela curta, sem os governadores, HF fora do ar) a
estimativa cai nas taxas fixas da ADR 0012 e diz o motivo.

Limitações documentadas: itens fixados no perfil podem entrar fora da janela e inflar levemente a
taxa; perfis que atingiram o teto da Coleta de origem têm taxa mínima (a real é maior).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from scripts.apify_backfill_shared import TAXA_POSTS_POR_DIA, TAXA_REELS_POR_DIA
from src.coleta import hf

MIN_DIAS_CALIBRACAO = 30
COLECOES_CALIBRADAS = ("posts", "reels")
TAXAS_FIXAS = {"posts": TAXA_POSTS_POR_DIA, "reels": TAXA_REELS_POR_DIA}


@dataclass(frozen=True)
class Calibracao:
    """Taxas por governador (itens por dia) e de onde vieram; `motivo_fallback` preenchido = taxas fixas."""

    n_governadores: int
    origem: str | None = None
    dias_janela: int | None = None
    taxas: dict[str, dict[str, float]] = field(default_factory=lambda: {c: {} for c in COLECOES_CALIBRADAS})
    taxa_media: dict[str, float] = field(default_factory=lambda: dict(TAXAS_FIXAS))
    perfis_calibrados: int = 0
    perfis_truncados: int = 0
    motivo_fallback: str | None = None

    @property
    def usa_taxas_fixas(self) -> bool:
        return self.motivo_fallback is not None

    def resumo(self) -> str:
        """Primeira linha da saída: a Coleta de origem ou as taxas fixas."""
        if self.usa_taxas_fixas:
            return f"taxas fixas da ADR 0012 ({TAXAS_FIXAS['posts']:.2f} posts / {TAXAS_FIXAS['reels']:.2f} reels por dia)".replace(".", ",")
        return self.origem or ""

    def detalhe(self) -> str:
        """Segunda linha da saída: o motivo do fallback ou a cobertura da calibração."""
        if self.usa_taxas_fixas:
            return self.motivo_fallback or ""
        texto = f"{self.dias_janela} dias; {self.perfis_calibrados}/{self.n_governadores} governadores com taxa propria"
        if self.perfis_truncados:
            texto += f"; {self.perfis_truncados} no teto (taxa minima)"
        return texto


def _fallback(motivo: str, n_governadores: int) -> Calibracao:
    return Calibracao(n_governadores=n_governadores, motivo_fallback=motivo)


def calibrar(coleta: hf.ColetaListada | None, usernames: Sequence[str]) -> Calibracao:
    """Taxa por governador e coleção a partir da cobertura da `coleta` anterior (função pura)."""
    n = len(usernames)
    if coleta is None:
        return _fallback("nenhuma Coleta anterior com manifesto no HF", n)
    janela = coleta.recorte.janela_efetiva(coleta.extraido_em.date())
    if janela is None:
        return _fallback("Coleta anterior sem janela (so teto)", n)
    dias = (janela[1] - janela[0]).days
    if dias < MIN_DIAS_CALIBRACAO:
        return _fallback(f"janela de {dias} dias e curta demais para calibrar (minimo {MIN_DIAS_CALIBRACAO})", n)

    governadores = {u.lower() for u in usernames}
    teto = coleta.recorte.teto
    taxas: dict[str, dict[str, float]] = {c: {} for c in COLECOES_CALIBRADAS}
    truncados: set[str] = set()
    for colecao in COLECOES_CALIBRADAS:
        for perfil in coleta.cobertura.get(colecao, {}).get("por_perfil", []):
            username = str(perfil["username"]).lower()
            if username not in governadores:
                continue
            taxas[colecao][username] = perfil["itens"] / dias
            if teto is not None and perfil["itens"] >= teto:
                truncados.add(username)
    calibrados = set().union(*(set(t) for t in taxas.values()))
    if not calibrados:
        return _fallback("nenhum governador na cobertura da Coleta anterior", n)

    media = {c: (sum(t.values()) / len(t) if t else TAXAS_FIXAS[c]) for c, t in taxas.items()}
    return Calibracao(
        n_governadores=n,
        origem=coleta.coleta,
        dias_janela=dias,
        taxas=taxas,
        taxa_media=media,
        perfis_calibrados=len(calibrados),
        perfis_truncados=len(truncados),
    )


def carregar_calibracao(cliente_factory: Callable[[], hf.ClienteColetaHF], usernames: Sequence[str]) -> Calibracao:
    """Calibra com a Coleta mais recente do HF. Qualquer falha do HF vira fallback com motivo: a estimativa
    nunca depende da rede."""
    try:
        coletas = hf.listar(cliente=cliente_factory())
    except Exception as erro:
        return _fallback(f"HF indisponivel ({type(erro).__name__})", len(usernames))
    return calibrar(coletas[0] if coletas else None, usernames)
