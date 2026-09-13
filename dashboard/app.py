"""Entrypoint do novo dashboard "por decisão" (ADR 0021).

A partir da issue #111 (Tela 1, "Resumo da semana"), este módulo é o
entrypoint real do produto -- substitui `app.py` (raiz, apagado nesta
issue) e `pages/01_explorar.py` (idem). Navegação por `st.radio` na
sidebar, não multipágina nativa do Streamlit (ver ADR 0021, "Estrutura
nova") -- cada entrada de `TELAS` é o `render()` de um módulo de
`dashboard/screens/*.py`, registrado aqui conforme cada tela é implementada
pelas próximas issues da sequência (#111-#116).

Rodar com: `streamlit run dashboard/app.py`.
"""

from __future__ import annotations

import os
import sys

import streamlit as st

ROOT_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dashboard.core.theme import inject_theme  # noqa: E402
from dashboard.screens import produzir, resumo  # noqa: E402

st.set_page_config(page_title="Growth — Assessoria", layout="wide")
inject_theme()

TELAS: dict[str, object] = {
    "Resumo da semana": resumo.render,
    "O que produzir": produzir.render,
}

st.sidebar.title("Growth — Assessoria")
tela_selecionada = st.sidebar.radio("Telas", options=list(TELAS.keys()))
TELAS[tela_selecionada]()
