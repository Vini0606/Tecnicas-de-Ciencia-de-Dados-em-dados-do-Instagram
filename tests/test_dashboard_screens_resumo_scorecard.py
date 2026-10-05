"""Testes da sub-aba Scorecard do Resumo (ADR 0030 / ADR 0031, issue #188).

Seam: funcoes puras de tela (linhas da tabela, formatacao pt-BR, destaque,
pendencia) + o carregador `data.load_governor_scorecard`."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
from deltalake.writer import write_deltalake

from config import settings
from dashboard.core import data
from dashboard.screens import resumo_scorecard as sc
from dashboard.screens.resumo_comum import TODOS_OS_GOVERNADORES

URL_A = "https://www.instagram.com/gov_a/"
URL_B = "https://www.instagram.com/gov_b/"
URL_C = "https://www.instagram.com/gov_c/"


def _linha(url, username, ranking, escore, *, consistencia=None, n_dim=4):
    return {
        "inputUrl": url,
        "username": username,
        "alcance_norm": 80.0,
        "ativacao_norm": 60.0,
        "qualidade_norm": 40.0,
        "profundidade_norm": 20.0,
        "consistencia_norm": consistencia if consistencia is not None else np.nan,
        "consistencia_pendente": consistencia is None,
        "n_dimensoes": n_dim,
        "escore": escore,
        "ranking": ranking,
    }


def _df():
    # Fora de ordem de proposito; C sem escore/ranking.
    return pd.DataFrame(
        [
            _linha(URL_C, "gov_c", np.nan, np.nan, n_dim=3),
            _linha(URL_B, "gov_b", 2, 50.0),
            _linha(URL_A, "gov_a", 1, 75.5, consistencia=90.0, n_dim=5),
        ]
    )


def test_linhas_ordenadas_pelo_ranking_gravado_e_sem_escore_por_ultimo():
    linhas = sc.montar_linhas(_df(), TODOS_OS_GOVERNADORES)
    assert [linha["nome"] for linha in linhas] == ["gov_a", "gov_b", "gov_c"]
    assert [linha["posicao"] for linha in linhas] == ["1", "2", "—"]


def test_selecionado_e_destacado_e_todos_nao_destaca():
    linhas = sc.montar_linhas(_df(), URL_B.upper().rstrip("/"))
    assert [linha["destacado"] for linha in linhas] == [False, True, False]
    todos = sc.montar_linhas(_df(), TODOS_OS_GOVERNADORES)
    assert not any(linha["destacado"] for linha in todos)


def test_consistencia_pendente_vira_pendente_sem_barra_e_nota_de_pesos():
    linhas = sc.montar_linhas(_df(), TODOS_OS_GOVERNADORES)
    cel = next(c for c in linhas[1]["dimensoes"] if c["chave"] == "consistencia")
    assert cel["pendente"] is True
    assert cel["texto"] == "pendente"
    assert cel["largura"] is None
    assert "4 dimensões" in linhas[1]["nota"]
    assert "0,25" in linhas[1]["nota"]
    # perfil com 5 dimensoes: sem nota
    assert linhas[0]["nota"] == ""


def test_perfil_sem_escore_mostra_traco_e_nota_propria():
    linha = sc.montar_linhas(_df(), TODOS_OS_GOVERNADORES)[2]
    assert linha["escore_texto"] == "—"
    assert "sem escore" in linha["nota"].lower()


def test_formatacao_pt_br():
    assert sc.fmt_valor(75.5) == "75,5"
    assert sc.fmt_valor(0.0) == "0,0"
    assert sc.fmt_valor(None) == "—"
    assert sc.fmt_valor(float("nan")) == "—"
    cel = sc.montar_linhas(_df(), TODOS_OS_GOVERNADORES)[0]["dimensoes"][0]
    assert cel["texto"] == "80,0" and cel["largura"] == 80.0


def test_legenda_de_pesos_menciona_pesos_renormalizados_so_quando_ha_pendencia():
    com_pend = sc.legenda_pesos(_df())
    assert "0,20" in com_pend and "0,25" in com_pend
    so_cinco = _df()[_df()["n_dimensoes"] == 5]
    assert "0,25" not in sc.legenda_pesos(so_cinco)


def test_nome_usa_metadata_quando_disponivel():
    meta = pd.DataFrame({"inputUrl": [URL_A], "nome": ["Governador A"]})
    linhas = sc.montar_linhas(_df(), TODOS_OS_GOVERNADORES, df_metadata=meta)
    assert linhas[0]["nome"] == "Governador A"
    assert linhas[1]["nome"] == "gov_b"


def test_tabela_vazia_ou_sem_colunas_nao_quebra():
    assert sc.montar_linhas(pd.DataFrame(), URL_A) == []
    assert sc.montar_linhas(pd.DataFrame({"x": [1]}), URL_A) == []


def test_html_escapa_nome_e_contem_pendente():
    df = _df()
    df.loc[df["username"] == "gov_b", "username"] = "<b>x</b>"
    html = sc.html_tabela(sc.montar_linhas(df, TODOS_OS_GOVERNADORES))
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;" in html
    assert "pendente" in html


def test_selo_de_confiabilidade_descreve_consistencia_e_plays():
    assert "tendência do engajamento" in sc.SELO_CONFIABILIDADE
    assert "reproduções" in sc.SELO_CONFIABILIDADE
    assert "crescimento de audiência" in sc.SELO_CONFIABILIDADE


def test_load_governor_scorecard_le_gold_e_degrada_para_vazio(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "GOLD_DIR", tmp_path / "gold")
    monkeypatch.setattr(settings, "SILVER_DIR", tmp_path / "silver")
    st.cache_resource.clear()
    st.cache_data.clear()
    assert data.load_governor_scorecard().empty
    write_deltalake(
        str(settings.GOLD_DIR / "governor_scorecard"),
        pd.DataFrame({"inputUrl": [URL_A], "escore": [10.0]}),
        mode="overwrite",
    )
    st.cache_data.clear()
    assert len(data.load_governor_scorecard()) == 1
    st.cache_resource.clear()
    st.cache_data.clear()
