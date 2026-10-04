"""Sub-aba Scorecard do Resumo (ADR 0030 / ADR 0031) -- placeholder.

A issue #188 substitui este módulo pelo ranking dos governadores por escore
composto. Até lá, apenas o aviso "em construção".
"""

from __future__ import annotations

import streamlit as st

AVISO_EM_CONSTRUCAO = (
    "Scorecard em construção -- o ranking por escore composto chega na próxima fatia."
)


def render(governor_url: str) -> None:
    st.info(AVISO_EM_CONSTRUCAO)
