"""Estimativa de custo da Coleta (issue #294): esperado x pior caso, preço por actor e plano."""

from __future__ import annotations

from datetime import date

import pytest

from src.coleta.custo import estimar_custo
from src.coleta.recorte import Recorte

HOJE = date(2026, 10, 13)


def test_referencia_90_dias_teto_250_26_governadores_plano_bronze():
    custo = estimar_custo(Recorte(dias=90, teto=250), 26, HOJE)

    # as taxas calibradas (7,22 posts e 5,19 reels por dia) passam de 250 em 90 dias:
    # o teto vale nas três coleções e esperado = pior caso
    assert custo["resultados_posts"] == 6500
    assert custo["resultados_reels"] == 6500
    assert custo["resultados_ugc"] == 6500
    assert custo["posts_reels"] == pytest.approx(29.90, abs=0.01)
    assert custo["ugc"] == pytest.approx(14.95, abs=0.01)
    assert custo["perfis"] == pytest.approx(0.06, abs=0.01)
    assert custo["total"] == pytest.approx(44.91, abs=0.01)
    assert custo["pior_caso_posts_reels"] == pytest.approx(29.90, abs=0.01)
    assert custo["pior_caso_ugc"] == pytest.approx(14.95, abs=0.01)
    assert custo["pior_caso_total"] == pytest.approx(44.91, abs=0.01)


def test_janela_curta_com_teto_alto_tem_esperado_menor_que_o_pior_caso():
    custo = estimar_custo(Recorte(dias=5, teto=250), 26, HOJE)

    assert custo["resultados_posts"] == pytest.approx(26 * 7.22 * 5)
    assert custo["resultados_reels"] == pytest.approx(26 * 5.19 * 5)
    assert custo["resultados_ugc"] == 26 * 250  # UGC sem calibração: teto cheio
    assert custo["total"] < custo["pior_caso_total"]
    assert custo["posts_reels"] < custo["pior_caso_posts_reels"]
    assert custo["ugc"] == pytest.approx(custo["pior_caso_ugc"])


def test_esperado_nunca_passa_do_pior_caso():
    for recorte in (Recorte(dias=1, teto=10), Recorte(dias=30, teto=100), Recorte(dias=90), Recorte(teto=30)):
        custo = estimar_custo(recorte, 26, HOJE)
        assert custo["total"] <= custo["pior_caso_total"] + 0.005
        assert custo["posts_reels"] <= custo["pior_caso_posts_reels"] + 0.005


def test_recorte_so_com_teto_usa_o_teto_cheio_como_esperado():
    custo = estimar_custo(Recorte(teto=10), 26, HOJE)

    assert custo["resultados_posts"] == 260
    assert custo["resultados_reels"] == 260
    assert custo["total"] == pytest.approx(custo["pior_caso_total"])
    assert 0 < custo["total"] < 5


def test_sem_teto_o_padrao_por_janela_define_o_pior_caso():
    custo = estimar_custo(Recorte(dias=90), 26, HOJE)

    # teto padrão: max(200, 10 x dias) = 900 por perfil e por coleção
    assert custo["pior_caso_ugc"] == pytest.approx(53.82, abs=0.01)
    assert custo["pior_caso_posts_reels"] == pytest.approx(107.64, abs=0.01)
    assert custo["pior_caso_total"] > custo["total"]


def test_outro_plano_muda_os_precos_e_plano_invalido_falha_claro():
    bronze = estimar_custo(Recorte(dias=90, teto=250), 26, HOJE, plano="BRONZE")["total"]
    gold = estimar_custo(Recorte(dias=90, teto=250), 26, HOJE, plano="GOLD")["total"]
    assert 0 < gold < bronze

    with pytest.raises(ValueError, match="plano"):
        estimar_custo(Recorte(dias=90, teto=250), 26, HOJE, plano="PLATINA")


def test_resultado_e_um_dicionario_plano_de_numeros_compativel_com_o_manifesto():
    custo = estimar_custo(Recorte(dias=90, teto=250), 26, HOJE)

    assert {"posts_reels", "ugc", "total"} <= set(custo)
    assert all(isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool) for k, v in custo.items())
