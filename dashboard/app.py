"""Entrypoint do novo dashboard "por decisão" (ADR 0021).

A partir da issue #111 (Tela 1, "Resumo da semana"), este módulo é o
entrypoint real do produto -- substitui `app.py` (raiz, apagado nesta
issue) e `pages/01_explorar.py` (idem). Navegação por `st.radio` na
sidebar, não multipágina nativa do Streamlit (ver ADR 0021, "Estrutura
nova") -- cada entrada de `TELAS` é o `render()` de um módulo de
`dashboard/screens/*.py`, registrado aqui conforme cada tela é implementada
pelas próximas issues da sequência (#111-#116).

`key="tela_selecionada"` no `st.radio` abaixo (issue #114, Tela 6/Funil):
qualquer tela pode trocar de aba programaticamente gravando o RÓTULO exato
de uma chave de `TELAS` em `st.session_state["tela_selecionada"]` e
chamando `st.rerun()` ANTES deste módulo recriar o widget -- no próximo
render, `st.radio` lê esse valor de `session_state` como seleção corrente
(Streamlit dá prioridade ao `session_state` já presente para a `key` do
widget sobre o parâmetro `index`). Ver `dashboard/screens/funil.py::render`
(bloco "O que fazer") para o primeiro uso real desse padrão.

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
from dashboard.screens import comparar, discurso_reacao, funil, produzir, radar, resumo  # noqa: E402

st.set_page_config(page_title="Growth — Assessoria", layout="wide")
inject_theme()

TELAS: dict[str, object] = {
    "Resumo da semana": resumo.render,
    "O que produzir": produzir.render,
    "Radar de crise": radar.render,
    "Comparar perfis": comparar.render,
    "Discurso x reação": discurso_reacao.render,
    "Funil de engajamento": funil.render,
}

st.sidebar.title("Growth — Assessoria")
tela_selecionada = st.sidebar.radio("Telas", options=list(TELAS.keys()), key="tela_selecionada")
TELAS[tela_selecionada]()
