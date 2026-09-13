"""Entrypoint do novo dashboard "por decisão" (ADR 0021 / issue #110).

Roda lado a lado com o `app.py`/`pages/*.py` antigos (raiz do projeto) até a
Tela 1 estar pronta -- ver ADR 0021, "Cutover": esta issue não apaga nada do
dashboard antigo, só constrói o esqueleto (`dashboard/core/*`) que as
próximas 6 issues (uma por tela) vão consumir.

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

st.set_page_config(page_title="Growth — Assessoria", layout="wide")
inject_theme()

# TELAS fica vazio nesta issue -- a Tela 1 ("Resumo da semana") é adicionada
# pela próxima issue da sequência ADR 0021 (issues #111-#116), junto com a
# navegação `st.radio` na sidebar que vai substituir este corpo temporário.
TELAS: dict[str, object] = {}

st.info("Dashboard em construção — telas chegam nas próximas issues.")
