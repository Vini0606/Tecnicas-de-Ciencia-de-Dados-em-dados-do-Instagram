"""Estimativa de custo da Coleta (issue #294): esperado x pior caso, preço por actor e plano."""

from __future__ import annotations

from datetime import date

import pytest

from src.coleta.custo import estimar_custo, teto_e_padrao
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


def test_quebra_por_actor_no_plano_bronze_e_no_gold_com_valores_exatos():
    bronze = estimar_custo(Recorte(dias=90, teto=250), 26, HOJE)
    for chave in ("posts", "reels", "ugc", "pior_caso_posts", "pior_caso_reels", "pior_caso_ugc"):
        assert bronze[chave] == pytest.approx(14.95, abs=0.01), chave  # 6.500 x US$ 2,30 / 1.000
    assert bronze["pior_caso_perfis"] == pytest.approx(0.06, abs=0.01)

    # Gold: posts 1,00 + 0,60 (post-details), reels 1,00, UGC 1,50, perfis 1,50 por 1.000
    gold = estimar_custo(Recorte(dias=90, teto=250), 26, HOJE, plano="gold")
    assert gold["posts"] == pytest.approx(10.40, abs=0.01)
    assert gold["reels"] == pytest.approx(6.50, abs=0.01)
    assert gold["ugc"] == pytest.approx(9.75, abs=0.01)
    assert gold["perfis"] == pytest.approx(0.04, abs=0.01)
    assert gold["total"] == pytest.approx(26.69, abs=0.01)


def test_teto_so_vale_quando_menor_que_o_volume_esperado():
    # 7,22 posts/dia x 30 dias = 216,6 < 250: o teto não limita posts; reels 5,19 x 30 = 155,7
    custo = estimar_custo(Recorte(dias=30, teto=250), 10, HOJE)
    assert custo["resultados_posts"] == pytest.approx(2166)
    assert custo["resultados_reels"] == pytest.approx(1557)

    # teto 100 < volume: vale o teto
    limitado = estimar_custo(Recorte(dias=30, teto=100), 10, HOJE)
    assert limitado["resultados_posts"] == 1000
    assert limitado["resultados_reels"] == 1000


def test_teto_e_padrao_so_quando_o_teto_nao_foi_informado():
    assert teto_e_padrao(Recorte(dias=90))
    assert not teto_e_padrao(Recorte(dias=90, teto=250))
    assert not teto_e_padrao(Recorte(teto=10))


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
