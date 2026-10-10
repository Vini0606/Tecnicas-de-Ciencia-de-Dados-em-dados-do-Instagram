"""Recorte, gramática da tag e estimativa de custo (ADR 0039, issue #246)."""

from datetime import date

import pytest

from src.coleta.custo import estimar_custo
from src.coleta.recorte import Recorte, gerar_tag, tag_valida

EXTRACAO = date(2026, 10, 9)


@pytest.mark.parametrize(
    ("recorte", "rotulo", "esperada"),
    [
        (Recorte(dias=90, teto=250), None, "coleta_2026-10-09_ultimos-90d_teto-250"),
        (Recorte(teto=10), None, "coleta_2026-10-09_teto-10"),
        (
            Recorte(inicio=date(2026, 3, 1), fim=date(2026, 6, 30)),
            None,
            "coleta_2026-10-09_de-2026-03-01_ate-2026-06-30",
        ),
        (
            Recorte(inicio=date(2026, 3, 1), fim=date(2026, 6, 30), teto=50),
            None,
            "coleta_2026-10-09_de-2026-03-01_ate-2026-06-30_teto-50",
        ),
        (Recorte(dias=90), "piloto", "coleta_2026-10-09_ultimos-90d_piloto"),
    ],
)
def test_gerar_tag_segue_a_gramatica(recorte, rotulo, esperada):
    tag = gerar_tag(recorte, EXTRACAO, rotulo)
    assert tag == esperada
    assert tag_valida(tag)


@pytest.mark.parametrize("rotulo", ["Piloto", "com espaço", "açúcar", "a_b", "-x", "", "teto-5", "ultimos-9d"])
def test_rotulo_invalido_e_recusado(rotulo):
    with pytest.raises(ValueError, match="Rótulo"):
        gerar_tag(Recorte(teto=10), EXTRACAO, rotulo)


@pytest.mark.parametrize(
    ("tag", "valida"),
    [
        ("coleta_2026-10-06_piloto", True),
        ("coleta_2026-10-09_ultimos-12m_teto-100", True),
        ("Coleta_2026-10-09_teto-10", False),
        ("coleta_2026-10-09_teto-10_ultimos-90d", False),
        ("coleta_2026-10-09 teto-10", False),
    ],
)
def test_tag_valida_distingue_a_gramatica(tag, valida):
    assert tag_valida(tag) is valida


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"dias": 90, "inicio": date(2026, 1, 1), "fim": date(2026, 2, 1)},
        {"inicio": date(2026, 1, 1)},
        {"inicio": date(2026, 6, 1), "fim": date(2026, 1, 1)},
        {"dias": 0},
        {"dias": -5},
        {"teto": 0},
        {"teto": -1},
    ],
)
def test_recortes_invalidos_sao_recusados_antes_de_qualquer_chamada(kwargs):
    with pytest.raises(ValueError):
        Recorte(**kwargs)


def test_intervalo_absoluto_extrai_desde_o_inicio_e_filtra_o_fim_localmente():
    recorte = Recorte(inicio=date(2026, 7, 1), fim=date(2026, 8, 31))
    assert recorte.dias_a_extrair(date(2026, 10, 1)) == 92
    assert recorte.dentro_do_recorte(date(2026, 7, 1))
    assert recorte.dentro_do_recorte(date(2026, 8, 31))
    assert not recorte.dentro_do_recorte(date(2026, 9, 1))
    assert not recorte.dentro_do_recorte(date(2026, 6, 30))


def test_recorte_so_com_teto_nao_tem_janela():
    recorte = Recorte(teto=10)
    assert not recorte.tem_janela
    assert recorte.dias_a_extrair(EXTRACAO) is None


def test_custo_de_90_dias_com_teto_250_para_26_governadores_bate_com_o_conhecido():
    custo = estimar_custo(Recorte(dias=90, teto=250), 26, EXTRACAO)
    assert custo["total"] == pytest.approx(37.82, abs=0.01)
    assert custo["posts_reels"] == pytest.approx(22.87, abs=0.01)
    assert custo["ugc"] == pytest.approx(14.95, abs=0.01)


def test_custo_so_com_teto_e_menor_que_o_de_uma_janela_longa():
    pequeno = estimar_custo(Recorte(teto=10), 26, EXTRACAO)["total"]
    grande = estimar_custo(Recorte(dias=90, teto=250), 26, EXTRACAO)["total"]
    assert 0 < pequeno < grande
