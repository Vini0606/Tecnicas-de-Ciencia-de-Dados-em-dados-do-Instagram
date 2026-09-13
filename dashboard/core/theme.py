"""Tema visual do novo dashboard (ADR 0021 / issue #110).

Duas paletas deliberadamente separadas (decisão já validada numa sessão de
`/grilling` anterior, ver ADR 0021 e memória do projeto,
`iesb_brand_chrome_dataviz_split.md`):

- `COLORS`: paleta semafórica (verde/amarelo/vermelho/azul) usada em faixas
  de decisão, KPIs e gráficos -- é, na prática, a paleta `/dataviz` desta
  reformulação (`ESPECIFICACAO_DASHBOARD.md`, seção 1.3).
- Chrome (navegação lateral, títulos de tela): vermelho institucional da
  IESB, reservado só para esse papel, nunca usado em gráfico ou KPI.

O hex do vermelho IESB (`#D92936`) não está hardcoded em nenhum lugar do
dashboard antigo (`app.py`/`src/dashboard/recommendations.py` não aplicam
tema algum -- a checagem foi feita nesta sessão) -- ele vem da decisão de
marca já registrada em memória do projeto na sessão de grilling de
2026-09-02 (manual de identidade visual da IESB). Reaproveitado aqui em vez
de reinventado, como pede a issue #110.
"""

from __future__ import annotations

import streamlit as st

COLORS = {
    "good": {"bg": "#E1F5EE", "fg": "#0F6E56"},
    "warn": {"bg": "#FAEEDA", "fg": "#854F0B"},
    "danger": {"bg": "#FCEBEB", "fg": "#A32D2D"},
    "info": {"bg": "#E6F1FB", "fg": "#185FA5"},
    "muted": "#5F5E5A",
}

# Chrome IESB -- só sidebar/títulos de tela, nunca dataviz (ver docstring
# do módulo).
_IESB_RED = "#D92936"
_IESB_BLACK = "#1D1D1B"


def inject_theme() -> None:
    """Injeta o CSS compartilhado por toda tela: faixa de decisão, rodapé e
    chrome de marca (sidebar/títulos em vermelho IESB + Inter). Chamado uma
    vez por `dashboard/app.py`."""
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', sans-serif;
        }}

        .decision-band {{
            border-radius: 12px;
            padding: 14px 18px;
            margin: 8px 0 18px;
        }}
        .decision-label {{
            font-size: 12px;
            opacity: .85;
            margin-bottom: 4px;
        }}
        .decision-text {{
            font-size: 17px;
            font-weight: 500;
            line-height: 1.4;
        }}
        .screen-footnote {{
            font-size: 12px;
            color: {COLORS["muted"]};
            margin-top: 24px;
        }}

        /* Chrome IESB -- navegação lateral e títulos de tela */
        section[data-testid="stSidebar"] {{
            border-right: 2px solid {_IESB_RED};
        }}
        h1, h2, h3 {{
            color: {_IESB_BLACK};
        }}
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {{
            color: {_IESB_RED};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
