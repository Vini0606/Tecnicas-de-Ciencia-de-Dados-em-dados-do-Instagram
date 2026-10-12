"""Seletor de período único das métricas de publicações (ADR 0041 / #281).

Um só componente para todas as telas: atalho "Todo o período", entrada
digitada "de DD/MM/AAAA até DD/MM/AAAA" e calendário. As datas só podem ficar
entre o menor e o maior dia com dado (`limites`). O estado é compartilhado
entre telas por `key` (a analista não reconfigura a cada tela); um intervalo
guardado que sai dos limites da tela atual é preso a eles, e o modo "todo o
período" acompanha os limites de cada tela.

A lógica de parse/limite está em `dashboard/core/periodo.py` (pura e testada);
aqui só há a cola com o Streamlit.
"""

from __future__ import annotations

import datetime

import streamlit as st

from dashboard.core.deltas import normalize_date_input_range
from dashboard.core.periodo import ajustar_intervalo, parse_intervalo_digitado

CHAVE_PADRAO = "periodo_publicacoes"
MENSAGEM_SEM_PUBLICACOES = "Nenhuma publicação no período selecionado."


def _fmt(d: datetime.date) -> str:
    return d.strftime("%d/%m/%Y")


def _texto_intervalo(inicio: datetime.date, fim: datetime.date) -> str:
    return f"de {_fmt(inicio)} até {_fmt(fim)}"


def seletor_periodo(
    limites: tuple[datetime.date, datetime.date],
    key: str = CHAVE_PADRAO,
) -> tuple[datetime.date, datetime.date]:
    """Desenha o seletor e devolve `(data_inicio, data_fim)` já presos a `limites`."""
    minimo, maximo = limites
    k_estado, k_todo = f"{key}_intervalo", f"{key}_todo"
    k_cal, k_txt = f"{key}_cal", f"{key}_txt"
    ss = st.session_state

    todo = ss.get(k_todo, True)
    if todo or k_estado not in ss:
        inicio, fim = minimo, maximo
    else:
        inicio, fim = ajustar_intervalo(*ss[k_estado], limites)
    ss[k_estado] = (inicio, fim)
    # Sincroniza os widgets ANTES de instanciá-los (o Streamlit só permite
    # escrever no estado de um widget antes dele existir nesta execução).
    # Seleção pela metade no calendário (só a 1ª data clicada): não sobrescreve,
    # senão a analista nunca consegue clicar a 2ª data.
    if len(ss.get(k_cal, (0, 0))) == 2:
        ss[k_cal] = (inicio, fim)
    ss[k_txt] = _texto_intervalo(inicio, fim)

    def _aplicar(novo_inicio: datetime.date, novo_fim: datetime.date) -> None:
        a, b = ajustar_intervalo(novo_inicio, novo_fim, limites)
        ss[k_estado] = (a, b)
        ss[k_todo] = (a, b) == (minimo, maximo)

    def _ao_clicar_todo() -> None:
        ss[k_todo] = True
        ss[k_estado] = (minimo, maximo)

    def _ao_digitar() -> None:
        lido = parse_intervalo_digitado(ss[k_txt])
        if lido is None:
            ss[f"{key}_erro"] = True
            return
        ss[f"{key}_erro"] = False
        _aplicar(*lido)

    def _ao_escolher_no_calendario() -> None:
        if len(ss[k_cal]) < 2:
            return
        _aplicar(*normalize_date_input_range(ss[k_cal]))

    st.button(
        "Todo o período", key=f"{key}_btn", on_click=_ao_clicar_todo, disabled=todo
    )
    st.text_input(
        "Período (digite)",
        key=k_txt,
        on_change=_ao_digitar,
        help="Formato: de DD/MM/AAAA até DD/MM/AAAA. Só vale dentro do intervalo com dados.",
    )
    st.date_input(
        "Período (data de publicação)",
        key=k_cal,
        min_value=minimo,
        max_value=maximo,
        format="DD/MM/YYYY",
        on_change=_ao_escolher_no_calendario,
    )
    if ss.pop(f"{key}_erro", False):
        st.caption(
            f"Não entendi o período. Use `de DD/MM/AAAA até DD/MM/AAAA`, entre "
            f"{_fmt(minimo)} e {_fmt(maximo)}."
        )
    return ss[k_estado]
