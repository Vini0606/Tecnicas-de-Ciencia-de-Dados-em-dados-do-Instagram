"""
Cliente minimo de download do Hugging Face usado pelo dashboard (ADR 0036).

Sobrou apenas o que `src/publicacao_hf.py` precisa para baixar Silver e Gold
na inicializacao do app. O sync de landing/Bronze e o escritor unico (ADR 0035)
foram removidos na contracao da issue #252: a publicacao, o download por tag e a
listagem de Coletas vivem em `src/coleta/hf.py` (ADR 0039).

O cliente HF e injetavel (`ClienteHF`), entao os testes nunca usam rede.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ErroHF(RuntimeError):
    """Falha na camada HF. A mensagem nunca carrega o token."""


class ClienteHF(Protocol):
    def baixar(self, pasta: Path, padroes: list[str], revisao: str | None = None) -> None: ...


class ClienteHFReal:
    """Cliente fino sobre `huggingface_hub`; erros saem sem o token."""

    def __init__(self, repo: str, token: str):
        self._repo = repo
        self._token = token

    def _falha(self, operacao: str, exc: Exception) -> ErroHF:
        detalhe = str(exc).replace(self._token, "***")
        return ErroHF(f"{operacao} falhou ({type(exc).__name__}): {detalhe}")

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
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira ErroHF sem o token
            raise self._falha("download do dataset", exc) from None
