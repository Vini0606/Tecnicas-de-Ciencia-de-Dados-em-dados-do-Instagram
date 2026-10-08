"""Controle de acesso do dashboard (ADR 0037).

No Streamlit Community Cloud, a restrição de visualizadores só protege a URL
principal: o caminho interno `/~/+/` e o seu WebSocket respondem sem login, e o
app executa e entrega o conteúdo a quem os abrir. Por isso o próprio app exige
uma senha, antes de baixar qualquer dado e de renderizar qualquer tela.

Regras (`decidir_acesso`):
- `APP_PASSWORD` configurada (Secrets ou `.env`): sempre pede a senha.
- Sem `APP_PASSWORD`, em `localhost`: libera (desenvolvimento local).
- Sem `APP_PASSWORD`, em qualquer outro host: BLOQUEIA (falha fechada), para um
  deploy sem a senha configurada nunca ficar aberto por esquecimento.

A senha é compartilhada (não há contas por pessoa). Quem precisar de acesso por
pessoa deve usar `st.login` (OIDC), fora do escopo desta ADR.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from collections.abc import Mapping

import streamlit as st

VAR_SENHA = "APP_PASSWORD"
CHAVE_SESSAO = "acesso_liberado"
ATRASO_SENHA_ERRADA = 1.0  # segundos; torna a tentativa em massa mais lenta

LIBERADO = "liberado"
PEDIR_SENHA = "pedir_senha"
BLOQUEADO = "bloqueado"

_HOSTS_LOCAIS = frozenset({"localhost", "127.0.0.1", "[::1]"})


def senha_confere(tentativa: str, esperada: str) -> bool:
    """Comparação em tempo constante (via hash, sem vazar o tamanho da senha)."""
    a = hashlib.sha256(tentativa.encode("utf-8")).digest()
    b = hashlib.sha256(esperada.encode("utf-8")).digest()
    return hmac.compare_digest(a, b)


def host_local(host: str | None) -> bool:
    """`True` para `localhost`, `127.0.0.1` e `[::1]` (com ou sem porta)."""
    if not host:
        return False
    nome = host.strip().lower()
    if nome.startswith("["):  # IPv6 literal: "[::1]:8501"
        nome = nome[: nome.find("]") + 1]
    else:
        nome = nome.split(":", 1)[0]
    return nome in _HOSTS_LOCAIS


def decidir_acesso(senha_esperada: str | None, host: str | None, liberado: bool) -> str:
    """`liberado`, `pedir_senha` ou `bloqueado` (ver o docstring do módulo)."""
    if senha_esperada:
        return LIBERADO if liberado else PEDIR_SENHA
    return LIBERADO if host_local(host) else BLOQUEADO


def _secrets() -> Mapping[str, object]:
    try:
        return {k: st.secrets[k] for k in st.secrets}
    except Exception:  # noqa: BLE001 - sem secrets.toml (uso local)
        return {}


def senha_configurada() -> str | None:
    valor = os.environ.get(VAR_SENHA) or _secrets().get(VAR_SENHA)
    senha = str(valor).strip() if valor else ""
    return senha or None


def _host_da_requisicao() -> str | None:
    try:
        return st.context.headers.get("Host")
    except Exception:  # noqa: BLE001 - AppTest e contextos sem requisição
        return None


def _formulario(esperada: str) -> None:
    st.title("Growth — Assessoria")
    st.caption("Acesso restrito. Informe a senha para continuar.")
    with st.form("acesso"):
        tentativa = st.text_input("Senha", type="password")
        enviado = st.form_submit_button("Entrar")
    if not enviado:
        return
    if senha_confere(tentativa, esperada):
        st.session_state[CHAVE_SESSAO] = True
        st.rerun()
    time.sleep(ATRASO_SENHA_ERRADA)
    st.error("Senha incorreta.")


def exigir_acesso() -> None:
    """Chamar no topo do app, antes de baixar dados e de renderizar telas.
    Interrompe a execução (`st.stop()`) enquanto o acesso não estiver liberado."""
    estado = decidir_acesso(
        senha_configurada(),
        _host_da_requisicao(),
        bool(st.session_state.get(CHAVE_SESSAO)),
    )
    if estado == LIBERADO:
        return
    if estado == BLOQUEADO:
        st.error(
            "Acesso não configurado: defina `APP_PASSWORD` nos Secrets do app para liberá-lo."
        )
        st.stop()
    _formulario(senha_configurada() or "")
    st.stop()
