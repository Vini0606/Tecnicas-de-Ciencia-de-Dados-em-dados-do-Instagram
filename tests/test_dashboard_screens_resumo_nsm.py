"""Testes da Tela 1 ("Resumo da semana", ADR 0021 / issue #111).

Só a lógica pura de `dashboard/screens/resumo.py` é testada aqui (nível do
semáforo, seleção dos 4 destaques) -- nunca a renderização Streamlit em si,
mesmo padrão de `tests/test_dashboard_core_data.py`/`test_dashboard_loaders.py`
(issue #50). Um bloco final testa alguns desses caminhos contra tabelas Delta
reais escritas em `tmp_path`, mesmo padrão dos dois arquivos acima."""

import inspect

import pandas as pd
import streamlit as st

from config import settings
from dashboard.core import data
from dashboard.screens import resumo_comum
from dashboard.screens import resumo_nsm as resumo


def _clear_caches():
    st.cache_resource.clear()
    st.cache_data.clear()


def _point_settings_at(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "GOLD_DIR", tmp_path / "gold")
    monkeypatch.setattr(settings, "SILVER_DIR", tmp_path / "silver")
    _clear_caches()


# ---------------------------------------------------------------------------
# Proporções de sentimento / formatação
# ---------------------------------------------------------------------------


def test_fmt_pct_arredonda_e_nao_mostra_float_bruto():
    # Regressão direta da user story 11 -- nunca "71.428571%".
    assert resumo._fmt_pct(0.71428571) == "71.4%"


def test_fmt_pct_com_none_mostra_placeholder():
    assert resumo._fmt_pct(None) == "—"


def test_fmt_int_br_usa_separador_de_milhar():
    assert resumo._fmt_int_br(12345) == "12.345"


# ---------------------------------------------------------------------------
# Destaques removidos (ADR 0026 / issue #154) -- prova estrutural de que
# não sobrou duplicata morta em resumo.py depois da migração.
# ---------------------------------------------------------------------------


def test_destaques_antigos_nao_estao_mais_em_resumo():
    for nome in (
        "_melhor_post",
        "_maior_alta_negatividade",
        "_topico_alto_positivo_baixo_discurso",
        "_contagem_publicacoes_recentes",
        "_intervalo_disponivel",
        "SEM_DADO_DISCURSO",
    ):
        assert not hasattr(resumo, nome), nome


# ---------------------------------------------------------------------------
# Governador (seleção / normalização de URL)
# ---------------------------------------------------------------------------


def test_governor_options_mapeia_nome_para_input_url():
    df_metadata = pd.DataFrame(
        {
            "inputUrl": [
                "https://www.instagram.com/gov_b/",
                "https://www.instagram.com/gov_a/",
            ],
            "nome": ["Governador B", "Governador A"],
        }
    )
    opcoes = resumo_comum._governor_options(df_metadata)
    assert opcoes == {
        "Governador A": "https://www.instagram.com/gov_a/",
        "Governador B": "https://www.instagram.com/gov_b/",
    }


def test_governor_options_vazio_quando_metadata_vazia():
    assert resumo_comum._governor_options(pd.DataFrame()) == {}


def test_filtrar_por_governador_normaliza_barra_final_e_caixa():
    df = pd.DataFrame({"inputUrl": ["HTTPS://www.instagram.com/gov_a"]})
    filtrado = resumo_comum._filtrar_por_governador(
        df, "https://www.instagram.com/gov_a/"
    )
    assert len(filtrado) == 1


# ---------------------------------------------------------------------------
# Contra tabelas Delta reais (tmp_path) -- mesmo padrão de
# tests/test_dashboard_core_data.py / test_dashboard_loaders.py (issue #50)
# ---------------------------------------------------------------------------


def test_load_reels_content_retorna_vazio_quando_silver_nao_existe(
    tmp_path, monkeypatch
):
    _point_settings_at(monkeypatch, tmp_path)

    out = data.load_reels_content()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


# ---------------------------------------------------------------------------
# "Todos os Governadores" (ADR 0027 / issue #161) -- filtro por governador
# ou sentinela "Todos" (helper compartilhado em `resumo_comum`).
# ---------------------------------------------------------------------------


def test_filtrar_por_governador_ou_todos_devolve_tudo_para_sentinela():
    df = pd.DataFrame({"inputUrl": ["a", "b"], "valor": [1, 2]})
    out = resumo_comum._filtrar_por_governador_ou_todos(
        df, resumo_comum.TODOS_OS_GOVERNADORES
    )
    assert len(out) == 2


def test_filtrar_por_governador_ou_todos_filtra_normalmente_para_url_real():
    df = pd.DataFrame({"inputUrl": ["a", "b"], "valor": [1, 2]})
    out = resumo_comum._filtrar_por_governador_ou_todos(df, "a")
    assert len(out) == 1
    assert out["valor"].iloc[0] == 1


def test_subaba_nsm_nao_tem_faixa_de_decisao_nem_kpis():
    """A sub-aba NSM mostra só o contraste de rankings: a faixa de decisão, a
    linha de KPIs e o bloco Crescimento foram removidos."""
    codigo = inspect.getsource(resumo)
    for removido in ("decision_band", "kpi_row", "##### Crescimento"):
        assert removido not in codigo


# ---------------------------------------------------------------------------
# Contraste de rankings bruto x NSM (issue #187)
# ---------------------------------------------------------------------------


def _tabela(linhas):
    """linhas: [(chave, bruto, nsm, pct_pos, pct_neg)]; nome = chave."""
    return pd.DataFrame(
        [
            {
                "chave": c,
                "nome": c,
                "bruto": b,
                "nsm": n,
                "pct_pos": p,
                "pct_neg": g,
            }
            for c, b, n, p, g in linhas
        ]
    )


def test_etiqueta_mudanca_subiu_caiu_igual_e_ausente():
    assert resumo.etiqueta_mudanca(5, 2) == "SUBIU"
    assert resumo.etiqueta_mudanca(2, 5) == "CAIU"
    assert resumo.etiqueta_mudanca(3, 3) is None
    assert resumo.etiqueta_mudanca(None, 3) is None


def test_posicoes_desempata_por_nome_e_ignora_sem_valor():
    t = _tabela([("b", 10, 1, 0, 0), ("a", 10, None, 0, 0), ("c", 5, 3, 0, 0)])
    assert resumo.posicoes(t, "bruto") == {"a": 1, "b": 2, "c": 3}
    assert resumo.posicoes(t, "nsm") == {"c": 1, "b": 2}


def test_extremo_empate_deterministico_e_vazio():
    t = _tabela([("b", 1, 1, 0.5, 0.1), ("a", 1, 1, 0.5, 0.1), ("c", 1, 1, 0.2, 0.3)])
    assert resumo.extremo(t, "pct_pos") == ("a", 0.5)
    assert resumo.extremo(t, "pct_neg") == ("c", 0.3)
    assert resumo.extremo(t.iloc[0:0], "pct_pos") is None
    assert resumo.extremo(_tabela([("a", 1, 1, None, None)]), "pct_pos") is None


def _tabela_doze():
    # bruto decrescente p01..p12; NSM sobe p11 e p12 para o topo
    linhas = []
    for i in range(1, 13):
        nsm = {11: 100.0, 12: 90.0}.get(i, 50.0 - i)
        linhas.append((f"p{i:02d}", 1000 - i, nsm, 0.5, 0.1))
    return _tabela(linhas)


def test_linhas_ranking_top10_sem_selecionado_em_todos():
    linhas = resumo.linhas_ranking(_tabela_doze(), "bruto", None)
    assert [item["posicao"] for item in linhas] == list(range(1, 11))
    assert not any(item["selecionado"] or item["extra"] for item in linhas)


def test_linhas_ranking_selecionado_fora_do_top10_ganha_linha_extra():
    linhas = resumo.linhas_ranking(_tabela_doze(), "bruto", "p12")
    assert len(linhas) == 11
    assert linhas[-1]["extra"] and linhas[-1]["selecionado"]
    assert linhas[-1]["posicao"] == 12


def test_linhas_ranking_selecionado_dentro_do_top10_so_destaca():
    linhas = resumo.linhas_ranking(_tabela_doze(), "bruto", "p03")
    assert len(linhas) == 10
    assert [i["posicao"] for i in linhas if i["selecionado"]] == [3]


def test_linhas_ranking_nsm_etiquetas_subiu_caiu_e_igual():
    linhas = resumo.linhas_ranking(_tabela_doze(), "nsm", None, com_etiqueta=True)
    por_nome = {i["nome"]: i for i in linhas}
    assert por_nome["p11"]["posicao"] == 1
    assert por_nome["p11"]["etiqueta"] == "SUBIU"
    assert por_nome["p01"]["etiqueta"] == "CAIU"
    t = _tabela([("a", 2, 2, 0, 0), ("b", 1, 1, 0, 0)])
    assert all(
        i["etiqueta"] is None
        for i in resumo.linhas_ranking(t, "nsm", None, com_etiqueta=True)
    )


def test_linhas_ranking_selecionado_sem_nsm_nao_aparece_no_ranking_nsm():
    t = _tabela([("a", 2, 5.0, 0, 0), ("b", 1, None, 0, 0)])
    linhas = resumo.linhas_ranking(t, "nsm", "b", com_etiqueta=True)
    assert [i["nome"] for i in linhas] == ["a"]


def test_linhas_ranking_tabela_vazia():
    assert resumo.linhas_ranking(_tabela([]), "bruto", None) == []
    assert resumo.linhas_ranking(pd.DataFrame(), "nsm", "a") == []


def test_valor_cartao_nsm_selecionado_media_em_todos_e_sem_nsm():
    t = _tabela([("a", 1, 100.0, 0, 0), ("b", 1, 0.0, 0, 0), ("c", 1, None, 0, 0)])
    assert resumo.valor_cartao_nsm(t, "a") == 100.0
    assert resumo.valor_cartao_nsm(t, None) == 50.0
    assert resumo.valor_cartao_nsm(t, "c") is None
    assert resumo.valor_cartao_nsm(t.iloc[0:0], None) is None


def test_montar_tabela_contraste_indice_nome_e_proporcoes():
    df_nsm = pd.DataFrame(
        {
            "inputUrl": ["https://instagram.com/a/", "https://instagram.com/b"],
            "username": ["a", "b"],
            "total_engajamento": [100, 200],
            "nsm": [10.0, 30.0],
        }
    )
    df_com = pd.DataFrame(
        {
            "inputUrl": ["https://instagram.com/a"] * 4,
            "sentiment_label": ["positive", "positive", "negative", "neutral"],
        }
    )
    df_meta = pd.DataFrame({"inputUrl": ["https://instagram.com/a"], "nome": ["Gov A"]})
    t = resumo.montar_tabela_contraste(df_nsm, df_com, df_meta).set_index("chave")
    a, b = t.loc["https://instagram.com/a"], t.loc["https://instagram.com/b"]
    assert (a["nsm"], b["nsm"]) == (0.0, 100.0)
    assert a["nome"] == "Gov A" and b["nome"] == "b"
    assert a["pct_pos"] == 0.5 and a["pct_neg"] == 0.25
    assert pd.isna(b["pct_pos"])


def test_montar_tabela_contraste_vazia():
    t = resumo.montar_tabela_contraste(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    assert t.empty and "nsm" in t.columns


def test_montar_tabela_contraste_descarta_url_repetida():
    df_nsm = pd.DataFrame(
        {
            "inputUrl": ["https://instagram.com/a", "https://instagram.com/a/"],
            "username": ["a", "a"],
            "total_engajamento": [1, 2],
            "nsm": [1.0, 2.0],
        }
    )
    t = resumo.montar_tabela_contraste(df_nsm, pd.DataFrame(), pd.DataFrame())
    assert len(t) == 1
