"""
Distribuição dos dados coletados por um dataset privado no Hugging Face
(ADR 0035, issue #232).

Move `data/landing/` e `data/bronze/` entre máquinas, em layout espelho 1:1.
A lógica de decisão (o que subir, quando recusar) é pura, sobre um
`Inventario` local e um remoto; a integração com o HF fica em `ClienteHF`,
injetável, para os testes nunca chamarem a rede.

Escritor único: a landing não conflita (cada execução é uma pasta nova), mas
a Bronze é Delta só de acréscimos e duas máquinas extraindo divergem o
`_delta_log`. Por isso o `push` recusa quando o remoto tem versão que o local
não tem, e o `pull` recusa sobrescrever dado local ainda não enviado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Protocol

PADROES_SYNC = ["landing/**", "bronze/**"]
_VERSAO_DELTA = re.compile(r"^(\d{20})\.json$")


@dataclass(frozen=True)
class Inventario:
    """Pastas de landing e versões do `_delta_log` por tabela Bronze."""

    landing: frozenset[str] = frozenset()
    bronze: dict[str, frozenset[int]] = field(default_factory=dict)

    def versao_maxima(self, tabela: str) -> int | None:
        versoes = self.bronze.get(tabela)
        return max(versoes) if versoes else None


@dataclass(frozen=True)
class Plano:
    """Resultado do planejamento: o que mover, ou o motivo da recusa."""

    landing: tuple[str, ...] = ()
    bronze: tuple[str, ...] = ()
    versoes_bronze: dict[str, int] = field(default_factory=dict)
    recusa: str | None = None

    @property
    def vazio(self) -> bool:
        return not self.landing and not self.bronze

    @property
    def padroes(self) -> list[str]:
        return [f"landing/{r}/**" for r in self.landing] + [f"bronze/{t}/**" for t in self.bronze]


def inventario_de_caminhos(caminhos: Iterable[str]) -> Inventario:
    """Monta o inventário a partir de caminhos relativos a `data/` (separador `/`)."""
    landing: set[str] = set()
    bronze: dict[str, set[int]] = {}
    for caminho in caminhos:
        partes = caminho.replace("\\", "/").split("/")
        if len(partes) >= 3 and partes[0] == "landing":
            landing.add(partes[1])
        elif len(partes) >= 2 and partes[0] == "bronze":
            versoes = bronze.setdefault(partes[1], set())
            if len(partes) >= 4 and partes[2] == "_delta_log":
                m = _VERSAO_DELTA.match(partes[3])
                if m:
                    versoes.add(int(m.group(1)))
    return Inventario(frozenset(landing), {t: frozenset(v) for t, v in bronze.items()})


def inventario_local(data_dir: Path) -> Inventario:
    caminhos = []
    for sub in ("landing", "bronze"):
        base = data_dir / sub
        if base.is_dir():
            caminhos += [p.relative_to(data_dir).as_posix() for p in base.rglob("*") if p.is_file()]
    return inventario_de_caminhos(caminhos)


def planejar_push(local: Inventario, remoto: Inventario) -> Plano:
    """Sobe landing ausente no remoto e Bronze com versão local à frente."""
    for tabela, versoes_remotas in remoto.bronze.items():
        versoes_locais = local.bronze.get(tabela, frozenset())
        so_remoto = versoes_remotas - versoes_locais
        if not so_remoto:
            continue
        if versoes_locais - versoes_remotas:
            motivo = f"a Bronze '{tabela}' divergiu: local e remoto têm commits que o outro não tem"
        else:
            motivo = (
                f"a Bronze '{tabela}' remota está à frente "
                f"(v{max(versoes_remotas)} contra v{max(versoes_locais, default=-1)} local)"
            )
        return Plano(recusa=f"{motivo}. Faça `pull` antes de enviar.")

    landing = tuple(sorted(local.landing - remoto.landing))
    bronze = tuple(
        sorted(t for t, v in local.bronze.items() if v - remoto.bronze.get(t, frozenset()))
    )
    return Plano(landing, bronze, {t: local.versao_maxima(t) or 0 for t in bronze})


def planejar_pull(local: Inventario, remoto: Inventario, force: bool = False) -> Plano:
    """Baixa tudo do remoto; sem `force`, recusa se isso perderia dado local não enviado."""
    if not force:
        sem_envio = sorted(local.landing - remoto.landing)
        if sem_envio:
            return Plano(
                recusa=(
                    f"há landing local que ainda não foi enviada ({', '.join(sem_envio)}). "
                    "Faça `push` antes, ou use --force para sobrescrever."
                )
            )
        for tabela, versoes in sorted(local.bronze.items()):
            if versoes - remoto.bronze.get(tabela, frozenset()):
                return Plano(
                    recusa=(
                        f"a Bronze '{tabela}' local tem versões que o remoto não tem "
                        f"(v{max(versoes)}). Faça `push` antes, ou use --force para sobrescrever."
                    )
                )
    return Plano(
        tuple(sorted(remoto.landing)),
        tuple(sorted(remoto.bronze)),
        {t: remoto.versao_maxima(t) or 0 for t in remoto.bronze},
    )


def mensagem_de_commit(plano: Plano) -> str:
    """Cita os `run_id` novos e as versões da Bronze enviadas."""
    partes = []
    if plano.landing:
        partes.append("landing: " + ", ".join(plano.landing))
    if plano.bronze:
        partes.append("bronze: " + ", ".join(f"{t}@v{plano.versoes_bronze[t]}" for t in plano.bronze))
    return "push: " + "; ".join(partes)


def descrever_plano(acao: str, plano: Plano) -> str:
    if plano.recusa:
        return f"{acao}: RECUSADO -- {plano.recusa}"
    if plano.vazio:
        return f"{acao}: nada a fazer."
    linhas = [f"{acao}: plano"]
    linhas += [f"  landing/{r}" for r in plano.landing]
    linhas += [f"  bronze/{t} (v{plano.versoes_bronze[t]})" for t in plano.bronze]
    return "\n".join(linhas)


class ErroHF(RuntimeError):
    """Falha na camada HF. A mensagem nunca carrega o token."""


class ClienteHF(Protocol):
    def listar_arquivos(self, revisao: str | None = None) -> list[str]: ...

    def enviar(self, pasta: Path, padroes: list[str], mensagem: str) -> None: ...

    def baixar(self, pasta: Path, padroes: list[str], revisao: str | None = None) -> None: ...


class ClienteHFReal:
    """Cliente fino sobre `huggingface_hub`; erros saem sem o token."""

    def __init__(self, repo: str, token: str):
        from huggingface_hub import HfApi

        self._repo = repo
        self._token = token
        self._api = HfApi(token=token)

    def _falha(self, operacao: str, exc: Exception) -> ErroHF:
        detalhe = str(exc).replace(self._token, "***")
        return ErroHF(f"{operacao} falhou ({type(exc).__name__}): {detalhe}")

    def listar_arquivos(self, revisao: str | None = None) -> list[str]:
        try:
            return list(
                self._api.list_repo_files(self._repo, repo_type="dataset", revision=revisao)
            )
        except Exception as exc:
            raise self._falha("listagem do dataset", exc) from None

    def enviar(self, pasta: Path, padroes: list[str], mensagem: str) -> None:
        try:
            self._api.upload_folder(
                repo_id=self._repo,
                repo_type="dataset",
                folder_path=str(pasta),
                allow_patterns=padroes,
                ignore_patterns=["**/.gitkeep"],
                commit_message=mensagem,
            )
        except Exception as exc:
            raise self._falha("envio ao dataset", exc) from None

    def baixar(self, pasta: Path, padroes: list[str], revisao: str | None = None) -> None:
        from huggingface_hub import snapshot_download

        try:
            snapshot_download(
                self._repo,
                repo_type="dataset",
                token=self._token,
                local_dir=str(pasta),
                allow_patterns=padroes,
                revision=revisao,
            )
        except Exception as exc:
            raise self._falha("download do dataset", exc) from None
