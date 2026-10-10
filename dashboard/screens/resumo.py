"""Tela "Resumo da semana" -- contêiner de seletor único + sub-abas
(ADR 0031 / issue #183, spec #182).

Estrutura: seletor de governador (com "Todos os Governadores") acima de três
sub-abas, na ordem NSM -> Funil de engajamento -> Scorecard, com NSM como
padrão. O seletor vale para as três. Cada sub-aba vive em módulo próprio
(`resumo_nsm`, `resumo_funil`, `resumo_scorecard`), registrado em `SUBABAS`
abaixo, expondo `render(governor_url)` -- assim as fatias seguintes mexem em
arquivos diferentes.

A sub-aba ativa é guardada em `st.session_state[CHAVE_SUBABA]` (widget
`st.radio` horizontal, que só executa a sub-aba escolhida). Abrir uma
sub-aba a partir de outra tela (grava `session_state[CHAVE_SUBABA]` via
`on_click`) não é usado hoje: nenhuma ação aponta para o Funil.
"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from dashboard.core import data
from dashboard.core.components import footnote, stage_label
from dashboard.screens import resumo_funil, resumo_nsm, resumo_scorecard
from dashboard.screens.resumo_comum import (
    _LABEL_TODOS_OS_GOVERNADORES,
    _PLACEHOLDER_SEM_GOVERNADOR,
    TODOS_OS_GOVERNADORES,
    _governor_options,
)

SUBABA_NSM = "NSM"
SUBABA_FUNIL = "Funil de engajamento"
SUBABA_SCORECARD = "Scorecard"

# Ordem de exibição; a primeira é a padrão.
SUBABAS: dict[str, Callable[[str], None]] = {
    SUBABA_NSM: resumo_nsm.render,
    SUBABA_FUNIL: resumo_funil.render,
    SUBABA_SCORECARD: resumo_scorecard.render,
}

CHAVE_SUBABA = "resumo_subaba"


def _selecionar_governador() -> str | None:
    """Seletor único; devolve a URL, `TODOS_OS_GOVERNADORES` ou `None` (sem
    governador disponível)."""
    df_metadata = data.load_governors_metadata()
    options = _governor_options(df_metadata)
    if not options:
        df_engagement = data.load_engagement()
        if not df_engagement.empty and "inputUrl" in df_engagement.columns:
            urls = df_engagement["inputUrl"].dropna().unique().tolist()
            options = {url: url for url in urls}

    if not options:
        st.selectbox("Governador", options=[_PLACEHOLDER_SEM_GOVERNADOR], disabled=True)
        return None
    nomes = [_LABEL_TODOS_OS_GOVERNADORES, *options.keys()]
    nome = st.selectbox("Governador", options=nomes)
    return (
        TODOS_OS_GOVERNADORES if nome == _LABEL_TODOS_OS_GOVERNADORES else options[nome]
    )


def render() -> None:
    governor_url = _selecionar_governador()
    stage_label("Visão do funil inteiro")

    if governor_url is None:
        st.info(
            "Nenhum governador disponível ainda -- rode a pipeline "
            "(`uv run python coleta.py baixar <tag>`) para popular o dashboard."
        )
        footnote()
        return

    subaba = st.radio(
        "Sub-aba",
        options=list(SUBABAS.keys()),
        horizontal=True,
        key=CHAVE_SUBABA,
        label_visibility="collapsed",
    )
    SUBABAS[subaba](governor_url)
    footnote()
