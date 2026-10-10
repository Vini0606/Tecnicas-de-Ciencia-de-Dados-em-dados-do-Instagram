"""
Recorte: o pedido de uma Coleta (CONTEXT.md, ADR 0039) e a gramática da tag que
a identifica no Hugging Face (docs/agents/coletas.md).

Tudo aqui é puro (sem rede, sem relógio implícito): a data da extração e o
"hoje" entram como argumento.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# Prefixos reservados: um rótulo livre não pode imitar um segmento da gramática.
_ROTULO_RE = r"(?!(?:teto|ultimos|de)-)[a-z0-9]+(?:-[a-z0-9]+)*"
_ROTULO = re.compile(rf"^{_ROTULO_RE}$")
_DATA = r"\d{4}-\d{2}-\d{2}"
_TAG = re.compile(
    rf"^coleta_{_DATA}"
    rf"(_ultimos-\d+[dm]|_de-{_DATA}_ate-{_DATA})?"
    r"(_teto-\d+)?"
    rf"(_{_ROTULO_RE})?$"
)


@dataclass(frozen=True)
class Recorte:
    """Janela relativa (`dias`) **ou** intervalo absoluto (`inicio`/`fim`),
    mais teto de itens por perfil (`teto`). Ao menos um critério é exigido:
    um Recorte sem janela e sem teto extrairia tudo, sem limite de custo."""

    dias: int | None = None
    inicio: date | None = None
    fim: date | None = None
    teto: int | None = None

    def __post_init__(self) -> None:
        tem_intervalo = self.inicio is not None or self.fim is not None
        if self.dias is not None and tem_intervalo:
            raise ValueError("Recorte: use janela relativa (dias) OU intervalo (inicio/fim), não os dois")
        if self.dias is not None and self.dias <= 0:
            raise ValueError("Recorte: dias deve ser positivo")
        if tem_intervalo:
            if self.inicio is None or self.fim is None:
                raise ValueError("Recorte: o intervalo exige inicio e fim")
            if self.inicio > self.fim:
                raise ValueError("Recorte: inicio não pode ser depois de fim")
        if self.teto is not None and self.teto <= 0:
            raise ValueError("Recorte: teto deve ser positivo")
        if self.dias is None and not tem_intervalo and self.teto is None:
            raise ValueError("Recorte vazio: informe janela, intervalo ou teto")

    @property
    def tem_janela(self) -> bool:
        return self.dias is not None or self.inicio is not None

    def dias_a_extrair(self, hoje: date) -> int | None:
        """Quantos dias para trás a Apify precisa alcançar. O actor só oferece
        "posts mais novos que X" (data final não confirmada), então um
        intervalo absoluto extrai desde `inicio` até hoje e `fim` é aplicado
        localmente (ver `dentro_do_recorte`)."""
        if self.dias is not None:
            return self.dias
        if self.inicio is not None:
            return max((hoje - self.inicio).days, 1)
        return None

    def dentro_do_recorte(self, publicado_em: date) -> bool:
        """Filtro local do intervalo absoluto (início e fim)."""
        if self.inicio is None:
            return True
        return self.inicio <= publicado_em <= self.fim


def gerar_tag(recorte: Recorte, extracao: date, rotulo: str | None = None) -> str:
    """`coleta_<extração>[_<janela>][_<teto>][_<rótulo>]`, na ordem fixa."""
    partes = [f"coleta_{extracao.isoformat()}"]
    if recorte.dias is not None:
        partes.append(f"ultimos-{recorte.dias}d")
    elif recorte.inicio is not None:
        partes.append(f"de-{recorte.inicio.isoformat()}_ate-{recorte.fim.isoformat()}")
    if recorte.teto is not None:
        partes.append(f"teto-{recorte.teto}")
    if rotulo is not None:
        if not _ROTULO.match(rotulo):
            raise ValueError(
                f"Rótulo inválido {rotulo!r}: use minúsculas, dígitos e '-', sem acento nem espaço, e não comece com teto-, ultimos- ou de-"
            )
        partes.append(rotulo)
    return "_".join(partes)


def tag_valida(tag: str) -> bool:
    return bool(_TAG.match(tag))
