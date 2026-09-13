"""Componentes reutilizáveis do novo dashboard (ADR 0021 / issue #110).

Toda tela nova monta a mesma estrutura fixa -- frase de decisão → KPIs com
variação → prova (ver ADR 0021 e `ESPECIFICACAO_DASHBOARD.md`, Princípio de
design) -- com estes quatro componentes, em vez de duplicar HTML/CSS em cada
`screens/*.py`.

Sem teste de unidade para renderização HTML/CSS aqui (consistente com o
padrão já usado no dashboard antigo -- `app.py`/`pages/*.py` não têm teste
dedicado de renderização Streamlit; ver issue #110, Testing Decisions).
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from dashboard.core.theme import COLORS


def decision_band(text: str, level: str = "info", label: str = "Recomendação") -> None:
    """A faixa colorida de decisão que abre cada tela -- a "Resposta" do
    princípio de design (sempre a primeira coisa lida)."""
    c = COLORS[level]
    st.markdown(
        f"""
        <div class="decision-band" style="background:{c['bg']};">
          <div class="decision-label" style="color:{c['fg']};">{label}</div>
          <div class="decision-text" style="color:{c['fg']};">{text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_row(items: Sequence[tuple]) -> None:
    """`items` = [(label, valor, delta_str, delta_dir[, help_text]), ...] --
    `delta_dir` ∈ {"up", "down", None} (mantido no contrato pela
    especificação, mas não usado diretamente aqui: `st.metric` já desenha a
    seta certa a partir do sinal de `delta`). Um 5º elemento opcional
    (`help_text`) vira o tooltip de `st.metric` -- adicionado na issue #111
    para o selo "em validação" do Engajamento qualificado (NSM), que precisa
    de um tooltip explicando a métrica sem virar um `st.warning` inteiro.
    Itens de 4 elementos continuam funcionando sem tooltip (`help=None`)."""
    cols = st.columns(len(items))
    for col, item in zip(cols, items, strict=True):
        label, value, delta, _direction = item[:4]
        help_text = item[4] if len(item) > 4 else None
        col.metric(label, value, delta=delta, help=help_text)


def footnote(text: str = "Análise baseada em comentários de Reels.") -> None:
    """Rodapé de ressalva de confiabilidade -- obrigatório em toda tela que
    usa sentimento de comentário (ver CONTEXT.md / ADR 0021, ressalva 1)."""
    st.markdown(f'<div class="screen-footnote">{text}</div>', unsafe_allow_html=True)


def stage_label(stage: str) -> None:
    """Rótulo discreto do estágio do funil COBRA-RACE no cabeçalho de cada
    tela (ver `ESPECIFICACAO_DASHBOARD.md`, "Rótulos de estágio por tela",
    para o texto exato de cada tela)."""
    st.markdown(
        f'<div style="font-size:12px;color:{COLORS["muted"]};margin:-6px 0 10px;">'
        f'<span style="border:0.5px solid #D3D1C7;border-radius:8px;padding:2px 10px;">'
        f"Funil · {stage}</span></div>",
        unsafe_allow_html=True,
    )
