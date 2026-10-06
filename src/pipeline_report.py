"""
Relatório de tabelas esperadas ao final do `pipeline.py` (issue #214).

O critério de validação de uma execução: cada tabela que o dashboard lê (e
as que o pipeline grava) existe, tem linhas e foi reescrita NESTA execução.
Fecha dois buracos: estágios de modelagem cuja exceção é engolida (ICE de
pautas, performance-por-post, cluster de perfil, Scorecard) e tabelas
`overwrite` que sobrevivem desatualizadas de execuções anteriores e
aparecem no dashboard como se fossem atuais.

Frescor = timestamp do último commit Delta, não `_run_id`: a Silver de
posts/reels herda o `_run_id` da Bronze (de uma extração antiga, quando a
Bronze é reaproveitada) e a modelagem cunha um `run_id` próprio -- o commit
Delta é a única evidência uniforme de "reescrita nesta execução".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

from deltalake import DeltaTable

from config import settings


class Status(Enum):
    OK = "OK"
    AUSENTE = "AUSENTE"
    VAZIA = "VAZIA"
    DESATUALIZADA = "DESATUALIZADA"
    NAO_SOLICITADA = "NAO SOLICITADA"


_STATUS_COM_PROBLEMA = {Status.AUSENTE, Status.VAZIA, Status.DESATUALIZADA}


@dataclass(frozen=True)
class TabelaEsperada:
    nome: str
    caminho: Path
    estagio: str  # "silver" | "gold" | "ugc" | "modelagem"
    usada_pelo_dashboard: bool


@dataclass(frozen=True)
class StatusTabela:
    tabela: TabelaEsperada
    status: Status
    linhas: int | None
    ultimo_commit: datetime | None

    @property
    def falhou(self) -> bool:
        return self.status in _STATUS_COM_PROBLEMA


def _t(caminho: Path, estagio: str, dashboard: bool) -> TabelaEsperada:
    return TabelaEsperada(Path(caminho).name, Path(caminho), estagio, dashboard)


# Ponto único do critério de validação. `usada_pelo_dashboard=True` deve
# bater exatamente com as tabelas que as Telas leem (teste anti-deriva em
# tests/test_pipeline_report.py).
TABELAS_ESPERADAS: tuple[TabelaEsperada, ...] = (
    _t(settings.SILVER_POSTS, "silver", True),
    _t(settings.SILVER_REELS, "silver", True),
    _t(settings.SILVER_GOVERNORS_METADATA, "silver", True),
    # Fallback de `DeltaRepository.load_comments` quando a Gold de sentimento
    # ainda não existe.
    _t(settings.SILVER_COMMENTS, "silver", True),
    _t(settings.SILVER_PROFILES, "silver", False),
    _t(settings.SILVER_POST_COMMENTS, "silver", False),
    _t(settings.GOLD_ENGAGEMENT, "gold", True),
    _t(settings.GOLD_ENGAGEMENT_HISTORY, "gold", False),
    _t(settings.SILVER_UGC_MENTIONS, "ugc", False),
    _t(settings.GOLD_UGC_MENTIONS, "ugc", True),
    _t(settings.GOLD_SENTIMENT, "modelagem", True),
    _t(settings.GOLD_SENTIMENT_HISTORY, "modelagem", True),
    _t(settings.GOLD_CLUSTERS_REELS, "modelagem", True),
    _t(settings.GOLD_PROFILE_CLUSTERS_ENGAGEMENT, "modelagem", True),
    _t(settings.GOLD_DISCOURSE_TOPICS, "modelagem", True),
    _t(settings.GOLD_TOPIC_PRIORITY_SCORE, "modelagem", True),
    _t(settings.GOLD_CONTENT_TOPIC_PRIORITY_SCORE, "modelagem", True),
    _t(settings.GOLD_NSM, "modelagem", True),
    _t(settings.GOLD_GOVERNOR_SCORECARD, "modelagem", True),
    _t(settings.GOLD_NSM_HISTORY, "modelagem", False),
    _t(settings.GOLD_CLUSTERS_POSTS, "modelagem", False),
    _t(settings.GOLD_POST_PERFORMANCE_COEFFICIENTS, "modelagem", False),
    _t(settings.GOLD_POST_PERFORMANCE_PREDICTIONS, "modelagem", False),
)


def ler_ultimo_commit(caminho: Path | str) -> datetime | None:
    """Timestamp (UTC) do último commit Delta; `None` se a tabela não existe."""
    if not DeltaTable.is_deltatable(str(caminho)):
        return None
    commit = DeltaTable(str(caminho)).history(1)[0]
    return datetime.fromtimestamp(commit["timestamp"] / 1000, tz=timezone.utc)


def contar_linhas(caminho: Path | str) -> int:
    return DeltaTable(str(caminho)).to_pyarrow_dataset().count_rows()


def avaliar_tabelas(
    tabelas: Iterable[TabelaEsperada],
    started_at: datetime,
    estagios_executados: set[str],
    ler_ultimo_commit: Callable[[Path], datetime | None] = ler_ultimo_commit,
    contar_linhas: Callable[[Path], int] = contar_linhas,
) -> list[StatusTabela]:
    """Precedência: NÃO SOLICITADA (estágio não rodou, nada é lido) >
    AUSENTE > DESATUALIZADA (último commit antes de `started_at`) > VAZIA > OK."""
    resultado = []
    for tabela in tabelas:
        if tabela.estagio not in estagios_executados:
            resultado.append(StatusTabela(tabela, Status.NAO_SOLICITADA, None, None))
            continue
        commit = ler_ultimo_commit(tabela.caminho)
        if commit is None:
            resultado.append(StatusTabela(tabela, Status.AUSENTE, None, None))
            continue
        linhas = contar_linhas(tabela.caminho)
        if commit < started_at:
            status = Status.DESATUALIZADA
        elif linhas == 0:
            status = Status.VAZIA
        else:
            status = Status.OK
        resultado.append(StatusTabela(tabela, status, linhas, commit))
    return resultado


def codigo_de_saida(resultado: Iterable[StatusTabela]) -> int:
    """1 se alguma tabela LIDA PELO DASHBOARD, de estágio executado, não está
    OK. Tabelas que só o pipeline usa (ex.: performance-por-post, que a ADR
    0019 pula legitimamente com pouco dado) aparecem como aviso no relatório,
    sem derrubar a execução."""
    return int(any(r.falhou and r.tabela.usada_pelo_dashboard for r in resultado))


def formatar_relatorio(resultado: list[StatusTabela], caminho_log: Path) -> str:
    """Tabela de texto sem emoji (o console cp1252 do Windows quebra)."""
    cabecalho = ("tabela", "estagio", "dashboard", "status", "linhas", "ultimo commit (UTC)")
    linhas = [
        (
            r.tabela.nome,
            r.tabela.estagio,
            "sim" if r.tabela.usada_pelo_dashboard else "nao",
            r.status.value,
            "-" if r.linhas is None else str(r.linhas),
            "-" if r.ultimo_commit is None else r.ultimo_commit.strftime("%Y-%m-%d %H:%M:%S"),
        )
        for r in resultado
    ]
    larguras = [max(len(str(c)) for c in coluna) for coluna in zip(cabecalho, *linhas)]

    def _linha(valores):
        return " | ".join(str(v).ljust(w) for v, w in zip(valores, larguras))

    contagem = {s: sum(r.status is s for r in resultado) for s in Status}
    resumo = ", ".join(f"{s.value}={n}" for s, n in contagem.items() if n)
    falhas = [r.tabela.nome for r in resultado if r.falhou and r.tabela.usada_pelo_dashboard]
    avisos = [r.tabela.nome for r in resultado if r.falhou and not r.tabela.usada_pelo_dashboard]
    partes = [
        "[RELATORIO] Tabelas esperadas:",
        _linha(cabecalho),
        "-+-".join("-" * w for w in larguras),
        *(_linha(linha) for linha in linhas),
        f"[RELATORIO] Resumo: {resumo}.",
    ]
    if falhas:
        partes.append(f"[RELATORIO] Tabelas do dashboard com problema: {', '.join(falhas)}.")
    if avisos:
        partes.append(f"[RELATORIO] Aviso (fora do dashboard): {', '.join(avisos)}.")
    if falhas or avisos:
        partes.append(
            "[RELATORIO] Estagios pulados ficam registrados nos logs do pipeline e da "
            f"modelagem (cada um sob o seu run_id) em: {caminho_log}"
        )
    return "\n".join(partes)
