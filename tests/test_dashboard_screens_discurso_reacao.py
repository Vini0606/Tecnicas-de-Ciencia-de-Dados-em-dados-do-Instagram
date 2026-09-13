"""Testes da Tela 5 ("Discurso x reação", ADR 0021 / issue #116).

Só a lógica pura de `dashboard/screens/discurso_reacao.py` é testada aqui
(projeção de rótulo bruto -> tema curado, distribuição percentual por tema,
tabela de gap e seleção de tema por direção) -- nunca a renderização
Streamlit em si, mesmo padrão de `tests/test_dashboard_screens_comparar.py`/
`radar.py`/`funil.py` (issues #113-#115).
"""

import pandas as pd

from dashboard.screens import discurso_reacao as tela

GOV_A = "https://www.instagram.com/governador_a/"


# ---------------------------------------------------------------------------
# _projetar_tema -- issue #116, Testing Decisions: rótulo mapeado, rótulo
# não mapeado -> "outros" sem lançar exceção.
# ---------------------------------------------------------------------------


def test_projetar_tema_rotulo_mapeado():
    rotulo_real = "3_asfalto_entregamos_canutama_farra"
    assert tela._projetar_tema(rotulo_real) == "obras"


def test_projetar_tema_rotulo_nao_mapeado_cai_em_outros():
    assert tela._projetar_tema("um_rotulo_qualquer_nunca_visto") == tela._TEMA_OUTROS


def test_projetar_tema_none_cai_em_outros():
    assert tela._projetar_tema(None) == tela._TEMA_OUTROS


def test_projetar_tema_nan_cai_em_outros():
    assert tela._projetar_tema(float("nan")) == tela._TEMA_OUTROS


def test_projetar_tema_topic_menos_um_nunca_curado():
    """Convenção documentada no módulo: `Topic == -1` (ruído do BERTopic) em
    QUALQUER um dos dois modelos nunca recebe um tema de negócio curado --
    mesmo raciocínio de `comparar.py` para `cluster_label == -1`."""
    assert "-1_bora_daquipramelhor_seguimos_juntos" not in tela._MAPA_ROTULO_TEMA
    assert "-1_tecla_4_coração_azul_tecla_5_coração_verde" not in tela._MAPA_ROTULO_TEMA


# ---------------------------------------------------------------------------
# _distribuicao_percentual_por_tema
# ---------------------------------------------------------------------------


def test_distribuicao_percentual_por_tema_soma_um():
    df = pd.DataFrame(
        {
            "Name": [
                "3_asfalto_entregamos_canutama_farra",  # obras
                "3_asfalto_entregamos_canutama_farra",  # obras
                "0_arruinou_descaso_estrago_ridículo",  # crítica e insatisfação
                "rotulo_desconhecido",  # outros
            ]
        }
    )
    dist = tela._distribuicao_percentual_por_tema(df)
    assert dist["obras"] == 0.5
    assert dist["crítica e insatisfação"] == 0.25
    assert dist[tela._TEMA_OUTROS] == 0.25
    assert sum(dist.values()) == 1.0


def test_distribuicao_percentual_por_tema_dataframe_vazio():
    dist = tela._distribuicao_percentual_por_tema(pd.DataFrame())
    assert all(v == 0.0 for v in dist.values())
    assert set(dist.keys()) == set(tela._ordem_temas_exibicao())


def test_distribuicao_percentual_por_tema_sem_coluna_name():
    dist = tela._distribuicao_percentual_por_tema(pd.DataFrame({"outra_coluna": [1, 2]}))
    assert all(v == 0.0 for v in dist.values())


# ---------------------------------------------------------------------------
# _montar_tabela_gap / _tema_produzir_mais / _tema_reduzir_reformular /
# _tema_decisao -- issue #116, Testing Decisions: função pura de cálculo do
# gap + seleção do tema de maior gap em cada direção, DataFrames sintéticos.
# ---------------------------------------------------------------------------


def _tabela_gap_sintetica() -> pd.DataFrame:
    dist_discurso = {"obras": 0.5, "economia": 0.1, "educação": 0.0}
    dist_reacao = {"obras": 0.1, "economia": 0.1, "educação": 0.6}
    # Completa os demais temas com 0.0 nos dois lados para simular o
    # contrato real de `_distribuicao_percentual_por_tema` (todos os temas
    # de `_ordem_temas_exibicao()` sempre presentes).
    for tema in tela._ordem_temas_exibicao():
        dist_discurso.setdefault(tema, 0.0)
        dist_reacao.setdefault(tema, 0.0)
    return tela._montar_tabela_gap(dist_discurso, dist_reacao)


def test_montar_tabela_gap_calcula_reacao_menos_discurso():
    tabela = _tabela_gap_sintetica()
    linha_obras = tabela[tabela["tema"] == "obras"].iloc[0]
    assert linha_obras["gap"] == 0.1 - 0.5
    linha_educacao = tabela[tabela["tema"] == "educação"].iloc[0]
    assert linha_educacao["gap"] == 0.6 - 0.0


def test_tema_produzir_mais_escolhe_maior_gap_positivo():
    tabela = _tabela_gap_sintetica()
    tema = tela._tema_produzir_mais(tabela)
    assert tema is not None
    assert tema["tema"] == "educação"
    assert tema["gap"] > 0


def test_tema_reduzir_reformular_escolhe_maior_gap_negativo():
    tabela = _tabela_gap_sintetica()
    tema = tela._tema_reduzir_reformular(tabela)
    assert tema is not None
    assert tema["tema"] == "obras"
    assert tema["gap"] < 0


def test_tema_produzir_mais_none_sem_gap_positivo():
    dist_discurso = dict.fromkeys(tela._ordem_temas_exibicao(), 0.5)
    dist_reacao = dict.fromkeys(tela._ordem_temas_exibicao(), 0.1)
    tabela = tela._montar_tabela_gap(dist_discurso, dist_reacao)
    assert tela._tema_produzir_mais(tabela) is None


def test_tema_reduzir_reformular_none_sem_gap_negativo():
    dist_discurso = dict.fromkeys(tela._ordem_temas_exibicao(), 0.1)
    dist_reacao = dict.fromkeys(tela._ordem_temas_exibicao(), 0.5)
    tabela = tela._montar_tabela_gap(dist_discurso, dist_reacao)
    assert tela._tema_reduzir_reformular(tabela) is None


def test_temas_acionaveis_exclui_outros():
    tabela = _tabela_gap_sintetica()
    acionaveis = tela._temas_acionaveis(tabela)
    assert tela._TEMA_OUTROS not in acionaveis["tema"].tolist()


def test_tema_decisao_escolhe_maior_valor_absoluto_entre_os_dois():
    tabela = _tabela_gap_sintetica()
    tema_produzir = tela._tema_produzir_mais(tabela)  # educação, gap = +0.6
    tema_reduzir = tela._tema_reduzir_reformular(tabela)  # obras, gap = -0.4
    decisao = tela._tema_decisao(tema_produzir, tema_reduzir)
    assert decisao is not None
    assert decisao["tema"] == "educação"


def test_tema_decisao_none_quando_nenhum_dos_dois_existe():
    assert tela._tema_decisao(None, None) is None


def test_tema_decisao_usa_o_unico_disponivel():
    tema_produzir = {"tema": "obras", "gap": 0.2, "pct_discurso": 0.1, "pct_reacao": 0.3}
    assert tela._tema_decisao(tema_produzir, None) == tema_produzir


# ---------------------------------------------------------------------------
# render() -- estado vazio (issue #116, user story 5): `governor_discourse_topics`
# vazia para o governador selecionado degrada para "dados ainda não
# disponíveis" sem calcular gap com metade do dado ausente.
# ---------------------------------------------------------------------------


def test_render_degrada_sem_dado_de_discurso(monkeypatch):
    calculou_gap = {"chamado": False}

    def _montar_tabela_gap_espiao(*args, **kwargs):
        calculou_gap["chamado"] = True
        return tela._montar_tabela_gap(*args, **kwargs)

    monkeypatch.setattr(tela, "_montar_tabela_gap", _montar_tabela_gap_espiao)
    monkeypatch.setattr(
        tela.data,
        "load_governors_metadata",
        lambda: pd.DataFrame({"inputUrl": [GOV_A], "nome": ["Governador A"]}),
    )
    monkeypatch.setattr(
        tela.data,
        "load_discourse_topics",
        lambda: pd.DataFrame(columns=["inputUrl", "Name", "Topic"]),
    )
    monkeypatch.setattr(tela.data, "load_engagement", lambda: pd.DataFrame())
    monkeypatch.setattr(tela.data, "load_sentiment", lambda: pd.DataFrame())

    tela.render()

    assert calculou_gap["chamado"] is False
