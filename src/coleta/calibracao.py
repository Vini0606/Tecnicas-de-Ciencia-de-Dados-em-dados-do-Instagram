"""Base de calibração da estimativa de custo com a Coleta vigente no HF (issues #299, ADR 0042).

A contagem de cada governador (posts, reels, UGC) vem da cobertura por perfil do manifesto da Coleta anterior,
por menor que seja a janela dela. Quando não há Coleta anterior utilizável (nenhuma, sem os governadores, HF fora do
ar) a estimativa cai no custo máximo e diz o motivo. A projeção para o novo Recorte está em `custo.py`.

Limitações documentadas: itens fixados no perfil podem entrar fora da janela e inflar levemente a contagem;
governadores que atingiram o teto da Coleta de origem estão censurados (a real é maior) e a projeção os sobe ao novo teto.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from src.coleta import hf
from src.coleta.custo import COLECOES_CALIBRADAS, teto_efetivo


@dataclass(frozen=True)
class Calibracao:
    """Contagens por governador da Coleta anterior e de onde vieram; `motivo_fallback` preenchido = sem base."""

    n_governadores: int
    origem: str | None = None
    dias_janela: int | None = None  # None: a base não tem janela em dias (só teto, ou um dia só)
    base_teto: int = 0  # teto aplicado na Coleta de origem (governador com contagem >= teto está censurado)
    n_perfis_base: int = 0  # perfis que a Coleta de origem leu (para distinguir governador novo de governador sem itens)
    contagens: dict[str, dict[str, int]] = field(default_factory=lambda: {c: {} for c in COLECOES_CALIBRADAS})
    perfis_calibrados: int = 0
    perfis_truncados: int = 0
    motivo_fallback: str | None = None

    @classmethod
    def sem_calibracao(cls, motivo: str, n_governadores: int) -> Calibracao:
        """Estimativa sem base: o estimado vale o máximo; `motivo` aparece na saída."""
        return cls(n_governadores=n_governadores, motivo_fallback=motivo)

    @property
    def usa_sem_base(self) -> bool:
        return self.motivo_fallback is not None

    def resumo(self) -> str:
        """Primeira linha da saída: a Coleta de origem ou a ausência de base."""
        if self.usa_sem_base:
            return "sem base de calibracao (estimado = maximo)"
        return self.origem or ""

    def detalhe(self) -> str:
        """Segunda linha da saída: o motivo do fallback ou a cobertura da calibração."""
        if self.usa_sem_base:
            return self.motivo_fallback or ""
        janela = f"{self.dias_janela} dias" if self.dias_janela else "sem janela em dias (posts e reels sem base)"
        texto = f"{janela}; {self.perfis_calibrados}/{self.n_governadores} governadores com itens na base"
        if self.perfis_truncados:
            texto += f"; {self.perfis_truncados} no teto (censurados)"
        return texto


def _fallback(motivo: str, n_governadores: int) -> Calibracao:
    return Calibracao.sem_calibracao(motivo, n_governadores)


def calibrar(coleta: hf.ColetaListada | None, usernames: Sequence[str]) -> Calibracao:
    """Contagem por governador e coleção a partir da cobertura da `coleta` anterior (função pura)."""
    n = len(usernames)
    if coleta is None:
        return _fallback("nenhuma Coleta anterior com manifesto no HF", n)
    janela = coleta.recorte.janela_efetiva(coleta.extraido_em.date())
    dias = (janela[1] - janela[0]).days if janela else 0

    governadores = {u.lower() for u in usernames}
    teto = teto_efetivo(coleta.recorte, coleta.extraido_em.date())  # inclui o teto padrão da Coleta de origem
    contagens: dict[str, dict[str, int]] = {c: {} for c in COLECOES_CALIBRADAS}
    truncados: set[str] = set()
    for colecao in COLECOES_CALIBRADAS:
        for perfil in coleta.cobertura.get(colecao, {}).get("por_perfil", []):
            username = str(perfil["username"]).lower()
            if username not in governadores:
                continue
            contagens[colecao][username] = int(perfil["itens"])
            if perfil["itens"] >= teto:
                truncados.add(username)
    calibrados = set().union(*(set(t) for t in contagens.values()))
    if not calibrados:
        return _fallback("nenhum governador na cobertura da Coleta anterior", n)

    return Calibracao(
        n_governadores=n,
        origem=coleta.coleta,
        dias_janela=dias if dias > 0 else None,
        base_teto=teto,
        n_perfis_base=int(coleta.cobertura.get("perfis", {}).get("itens", 0)),
        contagens=contagens,
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
    try:
        return calibrar(coletas[0] if coletas else None, usernames)
    except (KeyError, TypeError, ValueError, AttributeError) as erro:  # cobertura fora do formato esperado
        return _fallback(f"cobertura da Coleta anterior ilegivel ({type(erro).__name__})", len(usernames))
