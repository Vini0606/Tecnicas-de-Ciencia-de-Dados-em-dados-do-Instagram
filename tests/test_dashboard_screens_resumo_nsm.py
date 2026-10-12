"""Testes da Tela 1 ("Resumo da semana", ADR 0021 / issue #111).

Só a lógica pura de `dashboard/screens/resumo.py` é testada aqui (nível do
semáforo, seleção dos 4 destaques) -- nunca a renderização Streamlit em si,
mesmo padrão de `tests/test_dashboard_core_data.py`/`test_dashboard_loaders.py`
(issue #50). Um bloco final testa alguns desses caminhos contra tabelas Delta
reais escritas em `tmp_path`, mesmo padrão dos dois arquivos acima."""

import inspect

import numpy as np
import pandas as pd
import streamlit as st

from config import settings
from dashboard.core import data
from dashboard.core.tendencia import Tendencia
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


def test_linhas_ranking_lista_todos_os_perfis_sem_selecionado_em_todos():
    linhas = resumo.linhas_ranking(_tabela_doze(), "bruto", None)
    assert [item["posicao"] for item in linhas] == list(range(1, 13))
    assert not any(item["selecionado"] for item in linhas)


def test_linhas_ranking_destaca_o_selecionado_na_sua_posicao_real():
    linhas = resumo.linhas_ranking(_tabela_doze(), "bruto", "p12")
    assert len(linhas) == 12
    assert [i["posicao"] for i in linhas if i["selecionado"]] == [12]
    linhas = resumo.linhas_ranking(_tabela_doze(), "bruto", "p03")
    assert len(linhas) == 12
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


# ---------------------------------------------------------------------------
# Tendencia no cartao principal (ADR 0040 / issue #285) -- RASCUNHO PROVISORIO:
# metodo e limiares aguardam o backtest (#284). Substitui o Comparativo vs.
# mediana (ADR 0033) no NSM.
# ---------------------------------------------------------------------------


def _comentarios(chave, n_dias=40, efeito=0.0, seed=0):
    """Comentarios brutos de um perfil: 1 'dia' a cada 2 dias, 20 comentarios/dia."""
    rng = np.random.default_rng(seed)
    linhas = []
    for i in range(n_dias):
        p = min(0.95, 0.3 * (1 + efeito * i / max(n_dias - 1, 1)))
        data = (pd.Timestamp("2026-01-01") + pd.Timedelta(days=2 * i)).strftime(
            "%Y-%m-%dT12:00:00.000Z"
        )
        for j in range(20):
            linhas.append(
                {
                    "inputUrl": f"https://www.instagram.com/{chave}/",
                    "timestamp": data,
                    "sentiment_label": "positive" if rng.random() < p else "negative",
                    "id_comment": f"{chave}-{i}-{j}",
                    "origem_comentario": "reel" if j % 2 else "post",
                }
            )
    return pd.DataFrame(linhas)


def _chave(c):
    return resumo._normalize_url(pd.Series([f"https://www.instagram.com/{c}/"])).iloc[0]


def test_series_por_dia_conta_positivos_e_total_por_perfil_data_e_formato():
    s = resumo.series_sentimento_por_dia(_comentarios("a", n_dias=3))
    assert set(s.columns) == {"chave", "data", "formato", "positivos", "total"}
    assert len(s) == 6  # 3 dias x 2 formatos
    assert s["total"].sum() == 60
    assert (s["positivos"] <= s["total"]).all()
    assert "nsm" not in s.columns  # nunca o indice 0-100


def test_series_por_dia_sem_colunas_ou_vazio_devolve_vazio_e_ignora_data_invalida():
    assert resumo.series_sentimento_por_dia(pd.DataFrame()).empty
    assert resumo.series_sentimento_por_dia(pd.DataFrame({"x": [1]})).empty
    df = _comentarios("a", n_dias=2)
    df.loc[df.index[0], "timestamp"] = "lixo"
    assert resumo.series_sentimento_por_dia(df)["total"].sum() == 39


def test_tendencia_nsm_selecionado_sobe_e_cai():
    df = pd.concat(
        [_comentarios("a", efeito=1.0), _comentarios("b", efeito=-0.6, seed=1)]
    )
    assert resumo.tendencia_nsm(df, _chave("a")).estado == "Subindo"
    assert resumo.tendencia_nsm(df, _chave("b")).estado == "Caindo"


def test_tendencia_nsm_perfil_inexistente_ou_sem_dado_e_insuficiente():
    df = _comentarios("a", efeito=1.0)
    assert resumo.tendencia_nsm(df, _chave("zzz")).estado == "Dados insuficientes"
    assert (
        resumo.tendencia_nsm(pd.DataFrame(), _chave("a")).estado
        == "Dados insuficientes"
    )


def test_tendencia_nsm_de_um_governador_nao_muda_quando_os_outros_mudam():
    a = _comentarios("a", efeito=0.8)
    antes = resumo.tendencia_nsm(
        pd.concat([a, _comentarios("b", efeito=-0.7, seed=2)]), _chave("a")
    )
    depois = resumo.tendencia_nsm(
        pd.concat([a, _comentarios("b", efeito=1.5, seed=3), _comentarios("c")]),
        _chave("a"),
    )
    sozinho = resumo.tendencia_nsm(a, _chave("a"))
    assert antes == depois == sozinho


def test_tendencia_nsm_todos_e_mediana_dos_perfis():
    df = pd.concat(
        [_comentarios(c, efeito=1.0, seed=i) for i, c in enumerate("abcdefg")]
    )
    conj = resumo.tendencia_nsm(df, None)
    assert conj.estado == "Subindo" and conj.n_perfis == 7
    pouco = pd.concat([_comentarios(c, efeito=1.0, seed=i) for i, c in enumerate("ab")])
    assert resumo.tendencia_nsm(pouco, None).estado == "Dados insuficientes"


def test_html_tendencia_subindo_verde_caindo_vermelho_com_magnitude_e_incerteza():
    sobe = resumo.html_tendencia(Tendencia("Subindo", 0.123, 0.031, 0.22, 0.1, 40, 40))
    assert "▲ Subindo" in sobe and "+12,3%" in sobe and "IC 95%" in sobe
    assert "+3,1%" in sobe and "+22,0%" in sobe and "verde" in sobe
    cai = resumo.html_tendencia(Tendencia("Caindo", -0.2, -0.3, -0.1, -0.2, 40, 40))
    assert "▼ Caindo" in cai and "−20,0%" in cai and "verm" in cai


def test_html_tendencia_estavel_diz_sem_evidencia_e_nao_afirma_que_nada_mudou():
    est = resumo.html_tendencia(Tendencia("Estável", 0.02, -0.08, 0.13, 0.02, 40, 40))
    assert "Estável" in est and "sem evidência suficiente de mudança" in est
    assert "neutro" in est and "▲" not in est and "▼" not in est


def test_html_tendencia_dados_insuficientes_sem_seta_e_none_vazio():
    ins = resumo.html_tendencia(Tendencia("Dados insuficientes"))
    assert "Dados insuficientes" in ins and "▲" not in ins and "▼" not in ins
    assert resumo.html_tendencia(None) == ""


def test_legenda_tendencia_e_provisoria_e_nao_cita_o_comparativo_antigo():
    sel = resumo.legenda_tendencia(Tendencia("Subindo", 0.1, 0.01, 0.2, 0.1, 40, 40))
    assert "provisória" in sel and "série bruta" in sel and "0–100" in sel
    assert "mediana dos demais" not in sel
    todos = resumo.legenda_tendencia(
        Tendencia("Subindo", 0.1, 0.01, 0.2, 0.1, 0, 0, 12)
    )
    assert "mediana das tendências" in todos and "n = 12" in todos
    assert resumo.legenda_tendencia(None) == ""


def test_nsm_nao_tem_mais_o_comparativo_vs_mediana():
    fonte = inspect.getsource(resumo)
    for velho in ("comparativo_nsm", "html_seta", "legenda_comparativo"):
        assert velho not in fonte


def test_css_da_tendencia_neutra_tem_cor_propria():
    assert ".n-tend.neutro { color: var(--n-neutro)" in resumo._CSS_NSM


def test_html_cartao_coloca_a_tendencia_abaixo_do_valor():
    html = resumo._html_cartao("T", "62,3", "sub", "verde", tendencia="<b>TEND</b>")
    assert html.index("62,3") < html.index("TEND") < html.index("sub")
    assert "TEND" not in resumo._html_cartao("T", "62,3", "sub", None)


def test_html_ranking_lista_todos_em_container_rolavel_e_destaca_selecionado():
    linhas = resumo.linhas_ranking(_tabela_doze(), "nsm", "p12", com_etiqueta=True)
    html = resumo._html_ranking(linhas, "verde", resumo._fmt_nsm_0_100)
    assert 'class="n-scroll"' in html
    assert html.count('class="n-linha') == 12
    assert html.count("(selecionado)") == 1
    assert "SUBIU" in html and "CAIU" in html


# ---------------------------------------------------------------------------
# Melhor aprovação / Maior rejeição: mínimo de comentários (ADR 0038)
# ---------------------------------------------------------------------------


def _tabela_amostra() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "chave": ["a", "b", "c", "d"],
            "nome": ["Pequeno", "Medio", "Grande", "Sem comentarios"],
            "pct_pos": [1.0, 0.8, 0.6, float("nan")],
            "pct_neg": [0.0, 0.1, 0.5, float("nan")],
            "n_comentarios": [3, 40, 300, 0],
        }
    )


def test_extremo_com_amostra_ignora_perfis_com_poucos_comentarios():
    # "Pequeno" tem 100% positivo, mas só 3 comentários: não pode ser o melhor.
    assert resumo.extremo_com_amostra(_tabela_amostra(), "pct_pos") == (
        "Medio",
        0.8,
        40,
    )
    assert resumo.extremo_com_amostra(_tabela_amostra(), "pct_neg") == (
        "Grande",
        0.5,
        300,
    )


def test_extremo_com_amostra_respeita_o_minimo_pedido_e_devolve_none_sem_elegiveis():
    assert resumo.extremo_com_amostra(_tabela_amostra(), "pct_pos", minimo=1) == (
        "Pequeno",
        1.0,
        3,
    )
    assert resumo.extremo_com_amostra(_tabela_amostra(), "pct_pos", minimo=1000) is None
    assert resumo.extremo_com_amostra(pd.DataFrame(), "pct_pos") is None
    sem_coluna = _tabela_amostra().drop(columns=["n_comentarios"])
    assert resumo.extremo_com_amostra(sem_coluna, "pct_pos") is None


def test_tabela_contraste_traz_o_numero_de_comentarios_por_perfil():
    nsm = pd.DataFrame(
        {
            "inputUrl": ["https://instagram.com/a/", "https://instagram.com/b/"],
            "nsm": [1.0, 2.0],
            "username": ["a", "b"],
            "total_engajamento": [10.0, 20.0],
        }
    )
    comentarios = pd.DataFrame(
        {
            "inputUrl": ["https://instagram.com/a"] * 3,
            "sentiment_label": ["positive", "positive", "negative"],
        }
    )
    tabela = resumo.montar_tabela_contraste(nsm, comentarios, pd.DataFrame())
    por_chave = dict(zip(tabela["nome"], tabela["n_comentarios"], strict=True))
    assert por_chave == {"a": 3, "b": 0}
    assert resumo.MIN_COMENTARIOS_CARTAO == 30
