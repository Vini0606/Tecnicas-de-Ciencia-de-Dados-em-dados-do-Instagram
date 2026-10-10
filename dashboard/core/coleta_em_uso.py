"""Indica, de forma discreta, qual Coleta o dashboard esta mostrando (ADR 0039).

A Coleta vem do `manifesto.json` do Snapshot baixado junto com Silver e Gold:
tag, Recorte e cobertura. Sem manifesto (dado local antigo), mostra so a
revisao pedida (`main` ou `HF_DATASET_REVISAO`). Uma linha unica na barra
lateral, igual em todas as telas.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import streamlit as st

from config import settings
from dashboard.core.bootstrap_dados import configuracao_atual
from src.publicacao_hf import ler_manifesto


def _br(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def rotulo_revisao(revisao: str | None) -> str:
    return revisao or "main (Coleta vigente)"


def _recorte(r: dict[str, Any]) -> str:
    if r.get("dias") is not None:
        partes = [f"ultimos {r['dias']} dias"]
    elif r.get("inicio") and r.get("fim"):
        partes = [f"{_br(r['inicio'])} a {_br(r['fim'])}"]
    else:
        partes = []
    if r.get("teto") is not None:
        partes.append(f"teto {r['teto']} por perfil")
    return ", ".join(partes) or "sem recorte"


def _cobertura(m: dict[str, Any]) -> str:
    for fonte in ("posts", "reels"):
        c = m["cobertura"][fonte]
        if c["mais_antiga"] and c["mais_recente"]:
            return f"{_br(c['mais_antiga'])} a {_br(c['mais_recente'])}"
    return "sem dados"


def descrever_coleta(manifesto: dict[str, Any] | None) -> str | None:
    """Linha unica: tag, Recorte e cobertura. `None` sem manifesto."""
    if not manifesto:
        return None
    return (
        f"Coleta {manifesto['identidade']['tag']} | recorte: {_recorte(manifesto['recorte'])}"
        f" | cobertura: {_cobertura(manifesto)}"
    )


def mostrar_coleta() -> None:
    """Chamar na barra lateral do app, depois do download dos dados."""
    config = configuracao_atual()
    linha = descrever_coleta(ler_manifesto(settings.DATA_DIR))
    if linha is None:
        linha = f"Coleta: {rotulo_revisao(config.revisao if config else None)} (sem manifesto)"
    st.sidebar.caption(linha)
