"""
Publicacao, download e listagem de Snapshots no Hugging Face (ADR 0039, issue #249).

A `main` do dataset guarda so a Coleta vigente: `publicar` cria UM commit que
substitui Bronze, Silver, Gold e manifesto (apagando o que a Coleta anterior
tinha e o novo Snapshot nao tem). A Coleta e identificada pelo commit e pelo
identificador gerado pelo Recorte (`coleta_<...>`), gravado na mensagem
(`push: <identificador>`) e no manifesto; nenhuma tag e criada. As Coletas
anteriores continuam na historia da `main` e acessiveis pelo identificador, pelo
hash do commit ou por uma tag de uso (criada a mao, ex.: `reboot-iesb`).

Garantias, por construcao:
- nunca force-push e nunca cria, move ou apaga tag: o `ClienteColetaHF` nem
  oferece essas operacoes;
- identificador ja publicado e recusado antes de qualquer escrita;
- nada e enviado sem `confirmar(plano)` verdadeiro, e o plano traz o alvo exato;
- o limite de armazenamento (valor injetado) e conferido antes de enviar.

O cliente e injetavel (Protocol); os testes usam um fake em memoria. O unico
codigo que fala com a rede e `ClienteColetaHFReal`, fino e sem teste de rede.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

from src.coleta.manifesto import NOME_ARQUIVO, escrever_manifesto, validar_manifesto
from src.coleta.recorte import Recorte, gerar_tag, tag_valida

CAMADAS_DA_COLETA = ("bronze/", "silver/", "gold/")
_IGNORADOS = {".gitkeep"}
VAR_TOKEN = "HF_TOKEN"
VAR_REPO = "HF_DATASET_REPO"


class ErroColetaHF(RuntimeError):
    """Falha na camada de Coletas no HF. A mensagem nunca carrega o token."""


class ErroColetaExistente(ErroColetaHF):
    """O identificador gerado ja foi publicado na main: uma Coleta nunca e repetida."""


class ErroLimiteArmazenamento(ErroColetaHF):
    """O envio estouraria o limite de armazenamento do dataset."""


@dataclass(frozen=True)
class CommitHF:
    id: str
    mensagem: str


class ClienteColetaHF(Protocol):
    def listar_tags(self) -> dict[str, str]:
        """Tag -> id do commit para onde aponta."""
        ...

    def listar_commits(self) -> list[CommitHF]:
        """Commits da `main`, do mais recente para o mais antigo."""
        ...

    def listar_arquivos(self, revisao: str | None = None) -> list[str]: ...

    def ler_arquivo(self, caminho: str, revisao: str | None = None) -> bytes: ...

    def tamanho_dataset(self) -> int: ...

    def baixar(self, pasta: Path, revisao: str | None = None) -> None: ...

    def commit_substituicao(self, pasta: Path, apagar: list[str], mensagem: str) -> str: ...


@dataclass(frozen=True)
class Plano:
    """O alvo exato de uma publicacao, mostrado antes de qualquer escrita."""

    coleta: str
    adicionar: tuple[str, ...]
    substituir: tuple[str, ...]
    apagar: tuple[str, ...]
    bytes_envio: int
    bytes_em_uso: int
    limite_bytes: int | None

    def descrever(self) -> str:
        linhas = [
            f"Coleta: {self.coleta} (nenhuma tag sera criada)",
            (f"Commit unico na main: {len(self.adicionar)} novo(s), {len(self.substituir)} substituido(s), "
            f"{len(self.apagar)} apagado(s); envio de {self.bytes_envio} bytes."),
        ]
        for titulo, itens in (
            ("Adicionar", self.adicionar),
            ("Substituir", self.substituir),
            ("Apagar", self.apagar),
        ):
            linhas.append(f"{titulo}:")
            linhas += [f"  {i}" for i in itens] or ["  (nenhum)"]
        return "\n".join(linhas)


@dataclass(frozen=True)
class Resultado:
    plano: Plano
    publicado: bool
    commit: str | None = None

    @property
    def coleta(self) -> str:
        return self.plano.coleta


@dataclass(frozen=True)
class ColetaListada:
    coleta: str
    commit: str
    recorte: Recorte
    cobertura: dict[str, Any]
    extraido_em: datetime
    tags_de_uso: tuple[str, ...] = ()


# --- helpers -----------------------------------------------------------------


def _arquivos_do_snapshot(pasta: Path) -> dict[str, int]:
    return {
        p.relative_to(pasta).as_posix(): p.stat().st_size
        for p in sorted(pasta.rglob("*"))
        if p.is_file() and p.name not in _IGNORADOS
    }


def _da_coleta(caminho: str) -> bool:
    return caminho == NOME_ARQUIVO or caminho.startswith(CAMADAS_DA_COLETA)


def _ler_manifesto_local(pasta: Path) -> dict[str, Any]:
    arquivo = pasta / NOME_ARQUIVO
    if not arquivo.is_file():
        raise ErroColetaHF(f"Snapshot sem {NOME_ARQUIVO} em {pasta}: gere o manifesto antes de publicar")
    manifesto = json.loads(arquivo.read_text(encoding="utf-8"))
    validar_manifesto(manifesto)
    return manifesto


def _recorte_do(manifesto: dict[str, Any]) -> Recorte:
    r = manifesto["recorte"]
    return Recorte(
        dias=r.get("dias"),
        inicio=date.fromisoformat(r["inicio"]) if r.get("inicio") else None,
        fim=date.fromisoformat(r["fim"]) if r.get("fim") else None,
        teto=r.get("teto"),
    )


PREFIXOS_COMMIT = ("push: ", "restore: ")


def _identificador_do_commit(mensagem: str) -> str | None:
    """`push: <identificador>` / `restore: <identificador>` -> identificador valido, senao `None`."""
    for prefixo in PREFIXOS_COMMIT:
        if mensagem.startswith(prefixo):
            ident = mensagem[len(prefixo) :].strip()
            return ident if tag_valida(ident) else None
    return None


def _resolver(referencia: str, cliente: ClienteColetaHF) -> str:
    """Identificador de Coleta (commit mais recente que o publicou), tag de uso ou
    hash de commit -> id do commit. Levanta `ErroColetaHF` se nada bate."""
    commits = cliente.listar_commits()
    if tag_valida(referencia):
        for c in commits:
            if _identificador_do_commit(c.mensagem) == referencia:
                return c.id
    tags = cliente.listar_tags()
    if referencia in tags:
        return tags[referencia]
    for c in commits:
        if c.id == referencia or (len(referencia) >= 7 and c.id.startswith(referencia)):
            return c.id
    raise ErroColetaHF(
        f"Não encontrei a Coleta {referencia!r}: use um identificador coleta_*, uma tag de uso ou um hash de commit"
    )


def _tag_da_publicacao(manifesto: dict[str, Any], rotulo: str | None) -> str:
    """O identificador vem do manifesto; um rotulo novo e aplicado pela gramatica do Recorte."""
    if rotulo is None:
        return manifesto["identidade"]["tag"]
    extracao = datetime.fromisoformat(manifesto["identidade"]["extraido_em"]).date()
    return gerar_tag(_recorte_do(manifesto), extracao, rotulo)


# --- publicar ----------------------------------------------------------------


def planejar(
    snapshot_dir: Path | str,
    rotulo: str | None = None,
    *,
    cliente: ClienteColetaHF,
    limite_bytes: int | None = None,
) -> Plano:
    """Valida e calcula o alvo da publicacao sem escrever nada no HF.

    Levanta `ErroColetaExistente` (identificador ja publicado) ou `ErroLimiteArmazenamento`."""
    pasta = Path(snapshot_dir)
    manifesto = _ler_manifesto_local(pasta)
    coleta = _tag_da_publicacao(manifesto, rotulo)
    if any(_identificador_do_commit(c.mensagem) == coleta for c in cliente.listar_commits()):
        raise ErroColetaExistente(
            f"A Coleta {coleta} já foi publicada na main; use um rótulo diferente (nunca repetimos uma Coleta)"
        )

    local = _arquivos_do_snapshot(pasta)
    remoto = {c for c in cliente.listar_arquivos() if _da_coleta(c)}
    plano = Plano(
        coleta=coleta,
        adicionar=tuple(sorted(set(local) - remoto)),
        substituir=tuple(sorted(set(local) & remoto)),
        apagar=tuple(sorted(remoto - set(local))),
        bytes_envio=sum(local.values()),
        bytes_em_uso=cliente.tamanho_dataset(),
        limite_bytes=limite_bytes,
    )
    if limite_bytes is not None and plano.bytes_em_uso + plano.bytes_envio > limite_bytes:
        raise ErroLimiteArmazenamento(
            f"Publicar {plano.bytes_envio} bytes sobre {plano.bytes_em_uso} em uso passa do limite de {limite_bytes} bytes"
        )
    return plano


def publicar(
    snapshot_dir: Path | str,
    rotulo: str | None = None,
    *,
    cliente: ClienteColetaHF,
    confirmar: Callable[[Plano], bool],
    limite_bytes: int | None = None,
    tipo_commit: str = "push",
) -> Resultado:
    """Substitui a Coleta vigente da `main` por um unico commit (sem tag).

    `confirmar` recebe o `Plano` (alvo exato) e so se retornar verdadeiro algo
    e enviado. Recusas (Coleta ja publicada, limite, manifesto invalido) acontecem
    antes de qualquer escrita."""
    pasta = Path(snapshot_dir)
    plano = planejar(pasta, rotulo, cliente=cliente, limite_bytes=limite_bytes)
    if not confirmar(plano):
        return Resultado(plano, publicado=False)

    manifesto = _ler_manifesto_local(pasta)
    if manifesto["identidade"]["tag"] != plano.coleta:
        manifesto["identidade"]["tag"] = plano.coleta
        escrever_manifesto(pasta, manifesto)

    commit = cliente.commit_substituicao(pasta, list(plano.apagar), f"{tipo_commit}: {plano.coleta}")
    return Resultado(plano, publicado=True, commit=commit)


# --- baixar / listar ---------------------------------------------------------


def baixar(referencia: str, destino: Path | str, *, cliente: ClienteColetaHF) -> Path:
    """Traz o Snapshot completo (Bronze, Silver, Gold e manifesto) de uma Coleta,
    dada por identificador `coleta_*`, tag de uso ou hash de commit."""
    revisao = _resolver(referencia, cliente)
    pasta = Path(destino)
    pasta.mkdir(parents=True, exist_ok=True)
    cliente.baixar(pasta, revisao)
    _ler_manifesto_local(pasta)
    return pasta


ROTULO_RESTAURADA = "restaurada"


def restaurar(
    referencia: str,
    *,
    cliente: ClienteColetaHF,
    confirmar: Callable[[Plano], bool],
    rotulo: str = ROTULO_RESTAURADA,
    limite_bytes: int | None = None,
) -> Resultado:
    """Traz uma Coleta antiga de volta para a `main` como um NOVO commit, com
    identificador novo (`<janela>_<teto>_<rotulo>`, pela gramatica do Recorte).

    `referencia`: identificador `coleta_*`, tag de uso ou hash de commit. Reaproveita
    `baixar` e `publicar`: o historico nao e reescrito, o commit original continua
    intacto e nada usa force-push. `confirmar` recebe o `Plano` com o alvo exato.
    Restaurar a mesma Coleta duas vezes com o mesmo rotulo e recusado
    (`ErroColetaExistente`); use outro rotulo."""
    with tempfile.TemporaryDirectory(prefix="coleta_restaurar_") as tmp:
        pasta = baixar(referencia, Path(tmp) / "snapshot", cliente=cliente)
        return publicar(
            pasta, rotulo, cliente=cliente, confirmar=confirmar, limite_bytes=limite_bytes, tipo_commit="restore"
        )


def listar(*, cliente: ClienteColetaHF) -> list[ColetaListada]:
    """Coletas da historia da `main` (identificador, commit, Recorte, cobertura e
    tags de uso lidos do manifesto de cada commit), da mais recente para a mais
    antiga. Commits fora de `push:`/`restore:` ou sem manifesto valido sao ignorados."""
    tags = cliente.listar_tags()
    coletas: list[ColetaListada] = []
    for commit in cliente.listar_commits():
        ident = _identificador_do_commit(commit.mensagem)
        if ident is None:
            continue
        try:
            manifesto = json.loads(cliente.ler_arquivo(NOME_ARQUIVO, commit.id).decode("utf-8"))
            validar_manifesto(manifesto)
        except (OSError, ValueError, KeyError):
            continue
        coletas.append(
            ColetaListada(
                coleta=ident,
                commit=commit.id,
                recorte=_recorte_do(manifesto),
                cobertura=manifesto["cobertura"],
                extraido_em=datetime.fromisoformat(manifesto["identidade"]["extraido_em"]),
                tags_de_uso=tuple(sorted(t for t, alvo in tags.items() if alvo == commit.id)),
            )
        )
    return coletas


# --- cliente real (fino, sem teste de rede) -----------------------------------


class ClienteColetaHFReal:
    """Implementacao sobre `huggingface_hub`. Token e repo vem so do ambiente
    (`HF_TOKEN`, `HF_DATASET_REPO`); erros saem sem o token."""

    def __init__(self, repo: str | None = None, token: str | None = None):
        from huggingface_hub import HfApi

        self._repo = repo or os.environ.get(VAR_REPO, "")
        self._token = token or os.environ.get(VAR_TOKEN, "")
        if not self._repo or not self._token:
            raise ErroColetaHF(f"Defina {VAR_TOKEN} e {VAR_REPO} no ambiente")
        self._api = HfApi(token=self._token)

    def _falha(self, operacao: str, exc: Exception) -> ErroColetaHF:
        detalhe = str(exc).replace(self._token, "***")
        return ErroColetaHF(f"{operacao} falhou ({type(exc).__name__}): {detalhe}")

    def listar_tags(self) -> dict[str, str]:
        try:
            refs = self._api.list_repo_refs(self._repo, repo_type="dataset")
            return {t.name: t.target_commit for t in refs.tags}
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira ErroColetaHF sem o token
            raise self._falha("listagem de tags", exc) from None

    def listar_commits(self) -> list[CommitHF]:
        try:
            commits = self._api.list_repo_commits(self._repo, repo_type="dataset")
            return [CommitHF(id=c.commit_id, mensagem=c.title) for c in commits]
        except Exception as exc:  # noqa: BLE001
            raise self._falha("listagem de commits", exc) from None

    def listar_arquivos(self, revisao: str | None = None) -> list[str]:
        try:
            return list(self._api.list_repo_files(self._repo, repo_type="dataset", revision=revisao))
        except Exception as exc:  # noqa: BLE001
            raise self._falha("listagem do dataset", exc) from None

    def ler_arquivo(self, caminho: str, revisao: str | None = None) -> bytes:
        from huggingface_hub import hf_hub_download

        try:
            local = hf_hub_download(
                self._repo, caminho, repo_type="dataset", token=self._token, revision=revisao
            )
            return Path(local).read_bytes()
        except Exception as exc:  # noqa: BLE001
            raise self._falha(f"leitura de {caminho}", exc) from None

    def tamanho_dataset(self) -> int:
        try:
            info = self._api.dataset_info(self._repo, expand=["usedStorage"])
            usado = getattr(info, "used_storage", None)
            if usado is not None:
                return int(usado)
            info = self._api.dataset_info(self._repo, files_metadata=True)
            return sum(int(s.size or 0) for s in info.siblings or [])
        except Exception as exc:  # noqa: BLE001
            raise self._falha("consulta de armazenamento", exc) from None

    def baixar(self, pasta: Path, revisao: str | None = None) -> None:
        from huggingface_hub import snapshot_download

        try:
            snapshot_download(
                self._repo,
                repo_type="dataset",
                token=self._token,
                local_dir=str(pasta),
                allow_patterns=[f"{c}**" for c in CAMADAS_DA_COLETA] + [NOME_ARQUIVO],
                revision=revisao,
            )
        except Exception as exc:  # noqa: BLE001
            raise self._falha("download do dataset", exc) from None

    def commit_substituicao(self, pasta: Path, apagar: list[str], mensagem: str) -> str:
        from huggingface_hub import CommitOperationAdd, CommitOperationDelete

        try:
            operacoes: list[Any] = [CommitOperationDelete(path_in_repo=p) for p in apagar]
            for rel in _arquivos_do_snapshot(pasta):
                operacoes.append(CommitOperationAdd(path_in_repo=rel, path_or_fileobj=str(pasta / rel)))
            info = self._api.create_commit(
                self._repo, operations=operacoes, commit_message=mensagem, repo_type="dataset"
            )
            return str(info.oid)
        except Exception as exc:  # noqa: BLE001
            raise self._falha("commit de substituição", exc) from None
