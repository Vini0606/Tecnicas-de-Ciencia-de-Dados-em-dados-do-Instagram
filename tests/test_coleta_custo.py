"""Estimativa de custo da Coleta (ADR 0042): estimado (média + 3σ), máximo (teto cheio) e preço por actor e plano."""

from __future__ import annotations

import math
from datetime import date

import pytest

from src.coleta.calibracao import Calibracao
from src.coleta.custo import (
    SEM_BASE,
    agregar_custo_real,
    diferenca_percentual,
    estimar_custo,
    teto_e_padrao,
    teto_efetivo,
)
from src.coleta.recorte import Recorte

HOJE = date(2026, 10, 13)
BASE = "coleta_2026-10-06_ultimos-5d_teto-30"
COLECOES = ("perfis", "posts", "reels", "ugc")


def _base(contagens, *, n_perfis_base, n_governadores=None, dias=5, teto=30, origem=BASE) -> Calibracao:
    """Calibração montada à mão (a leitura do HF está em test_coleta_calibracao)."""
    completas = {c: {} for c in ("posts", "reels", "ugc")}
    completas.update(contagens)
    return Calibracao(
        n_governadores=n_governadores or n_perfis_base,
        origem=origem,
        dias_janela=dias,
        base_teto=teto,
        n_perfis_base=n_perfis_base,
        contagens=completas,
    )


# --- sem base: o estimado vale o máximo ---------------------------------------------------


def test_referencia_90_dias_teto_250_26_governadores_plano_bronze_sem_base():
    custo = estimar_custo(Recorte(dias=90, teto=250), 26, HOJE)

    # 26 x 250 = 6.500 itens por coleção, US$ 2,30 por 1.000 (posts 1,50 + 0,80 de post-details)
    assert custo["resultados_itens"] == {"perfis": 26, "posts": 6500, "reels": 6500, "ugc": 6500, "total": 19526}
    assert custo["maximo_usd"]["posts"] == pytest.approx(14.95, abs=0.001)
    assert custo["maximo_usd"]["reels"] == pytest.approx(14.951, abs=0.001)  # + US$ 0,001 de actor-start
    assert custo["maximo_usd"]["ugc"] == pytest.approx(14.95, abs=0.001)
    assert custo["maximo_usd"]["perfis"] == pytest.approx(0.0598, abs=0.0001)
    assert custo["maximo_usd"]["total"] == pytest.approx(44.911, abs=0.001)
    assert custo["estimado_usd"] == custo["maximo_usd"]  # sem base, estimado = máximo
    assert custo["base_calibracao"] == {"posts": SEM_BASE, "reels": SEM_BASE, "ugc": SEM_BASE}


def test_quebra_por_actor_no_plano_gold_com_valores_exatos():
    # Gold por 1.000: posts 1,00 + 0,60 (post-details), reels 1,00, UGC 1,50, perfis 1,50
    gold = estimar_custo(Recorte(dias=90, teto=250), 26, HOJE, plano="gold")["maximo_usd"]

    assert gold["posts"] == pytest.approx(10.40, abs=0.001)
    assert gold["reels"] == pytest.approx(6.501, abs=0.001)
    assert gold["ugc"] == pytest.approx(9.75, abs=0.001)
    assert gold["perfis"] == pytest.approx(0.039, abs=0.0001)
    assert gold["total"] == pytest.approx(26.69, abs=0.01)


def test_outro_plano_muda_os_precos_e_plano_invalido_falha_claro():
    bronze = estimar_custo(Recorte(dias=90, teto=250), 26, HOJE, plano="BRONZE")["maximo_usd"]["total"]
    gold = estimar_custo(Recorte(dias=90, teto=250), 26, HOJE, plano="GOLD")["maximo_usd"]["total"]
    assert 0 < gold < bronze

    with pytest.raises(ValueError, match="plano"):
        estimar_custo(Recorte(dias=90, teto=250), 26, HOJE, plano="PLATINA")


def test_teto_aplicado_e_se_veio_do_padrao():
    informado = estimar_custo(Recorte(dias=90, teto=250), 26, HOJE)["teto"]
    assert informado == {"aplicado_itens_por_perfil": 250, "padrao": False}

    padrao = estimar_custo(Recorte(dias=90), 26, HOJE)["teto"]
    assert padrao == {"aplicado_itens_por_perfil": 630, "padrao": True}  # max(200, 7 x 90)


def test_teto_padrao_por_janela_usa_o_piso_de_200_e_7_itens_por_dia():
    assert teto_efetivo(Recorte(dias=5), HOJE) == 200  # piso
    assert teto_efetivo(Recorte(dias=28), HOJE) == 200  # 7 x 28 = 196 < 200
    assert teto_efetivo(Recorte(dias=30), HOJE) == 210
    assert teto_efetivo(Recorte(dias=90), HOJE) == 630
    assert teto_efetivo(Recorte(teto=10), HOJE) == 10


def test_sem_teto_o_padrao_por_janela_define_o_maximo():
    custo = estimar_custo(Recorte(dias=90), 26, HOJE)

    # 26 x 630 = 16.380 itens por coleção
    assert custo["maximo_usd"]["ugc"] == pytest.approx(37.67, abs=0.01)
    assert custo["maximo_usd"]["total"] == pytest.approx(113.08, abs=0.01)


def test_teto_e_padrao_so_quando_o_teto_nao_foi_informado():
    assert teto_e_padrao(Recorte(dias=90))
    assert not teto_e_padrao(Recorte(dias=90, teto=250))
    assert not teto_e_padrao(Recorte(teto=10))


def test_recorte_so_com_teto_vale_o_teto_cheio():
    custo = estimar_custo(Recorte(teto=10), 26, HOJE)

    assert custo["resultados_itens"]["posts"] == 260
    assert custo["resultados_itens"]["reels"] == 260
    assert custo["estimado_usd"] == custo["maximo_usd"]
    assert 0 < custo["estimado_usd"]["total"] < 5


# --- com base: média + 3σ do total, limitada ao máximo ------------------------------------


def test_estimado_com_base_e_a_soma_projetada_mais_tres_desvios_do_total():
    # gov_a: 10 posts em 5 dias = 2/dia; gov_b não teve itens (ausente de por_perfil, mas estava na base)
    base = _base({"posts": {"gov_a": 10}}, n_perfis_base=2)
    custo = estimar_custo(Recorte(dias=30, teto=250), 2, HOJE, calibracao=base)

    # valores projetados [60, 0]: soma 60, σ populacional 30; 60 + 3 x sqrt(2) x 30 = 187,28 -> 188
    assert custo["resultados_itens"]["posts"] == math.ceil(60 + 3 * math.sqrt(2) * 30) == 188
    assert custo["maximo_usd"]["posts"] == pytest.approx(500 / 1000 * 2.3)
    assert custo["estimado_usd"]["posts"] == pytest.approx(188 / 1000 * 2.3)
    assert custo["estimado_usd"]["posts"] < custo["maximo_usd"]["posts"]
    assert custo["base_calibracao"]["posts"] == BASE


def test_o_estimado_nunca_passa_do_maximo():
    base = _base({"posts": {"gov_a": 10, "gov_b": 3}}, n_perfis_base=2)
    custo = estimar_custo(Recorte(dias=90, teto=250), 2, HOJE, calibracao=base)  # 3σ estouraria o teto

    assert custo["resultados_itens"]["posts"] == 500  # limitado ao máximo (2 x 250)
    assert custo["estimado_usd"]["posts"] == pytest.approx(custo["maximo_usd"]["posts"])


def test_posts_e_reels_projetam_pela_taxa_diaria_mas_o_ugc_pela_contagem():
    base = _base({"posts": {"gov_a": 5}, "reels": {"gov_a": 5}, "ugc": {"gov_a": 5}}, n_perfis_base=1)
    custo = estimar_custo(Recorte(dias=10, teto=250), 1, HOJE, calibracao=base)

    # 5 itens em 5 dias = 1/dia x 10 dias = 10; UGC não depende da janela: continua 5
    assert custo["resultados_itens"]["posts"] == 10
    assert custo["resultados_itens"]["reels"] == 10
    assert custo["resultados_itens"]["ugc"] == 5


def test_governador_no_teto_da_base_esta_censurado_e_sobe_ao_novo_teto():
    no_teto = estimar_custo(Recorte(dias=30, teto=250), 1, HOJE, calibracao=_base({"posts": {"gov_a": 30}}, n_perfis_base=1))
    abaixo = estimar_custo(Recorte(dias=30, teto=250), 1, HOJE, calibracao=_base({"posts": {"gov_a": 29}}, n_perfis_base=1))

    assert no_teto["resultados_itens"]["posts"] == 250  # bateu o teto 30 da base: pode ter muito mais
    assert abaixo["resultados_itens"]["posts"] == 174  # 29 / 5 x 30 dias


def test_o_novo_teto_limita_cada_governador():
    base = _base({"posts": {"gov_a": 20}}, n_perfis_base=1)
    custo = estimar_custo(Recorte(dias=90, teto=100), 1, HOJE, calibracao=base)

    assert custo["resultados_itens"]["posts"] == 100  # 20 / 5 x 90 = 360 -> teto 100


def test_governador_novo_no_elenco_entra_com_a_media_dos_demais():
    # a base leu 1 perfil (gov_a, 6 posts em 5 dias); o elenco cresceu para 3: b e c são novos
    base = _base({"posts": {"gov_a": 6}}, n_perfis_base=1, n_governadores=3)
    custo = estimar_custo(Recorte(dias=30, teto=250), 3, HOJE, calibracao=base)

    # projetados [36, 36, 36] (os novos pela média): σ = 0, estimado = 108
    assert custo["resultados_itens"]["posts"] == 108


def test_governador_que_estava_na_base_sem_itens_conta_zero_e_nao_a_media():
    base = _base({"posts": {"gov_a": 6, "gov_c": 6}}, n_perfis_base=3)  # gov_b leu-se e não teve itens
    custo = estimar_custo(Recorte(dias=30, teto=250), 3, HOJE, calibracao=base)

    # projetados [36, 36, 0]: soma 72, σ = sqrt(288) = 16,97
    assert custo["resultados_itens"]["posts"] == math.ceil(72 + 3 * math.sqrt(3) * math.sqrt(288))


def test_referencia_do_piloto_ugc_385_itens_de_6500():
    # piloto: 26 governadores, base de 5 dias e teto 30; UGC 234 itens, 11 governadores com 0 (ausentes de por_perfil)
    contagens = {f"gov_{i:02d}": n for i, n in enumerate([21] * 9 + [20, 14, 8, 1, 1, 1])}
    assert sum(contagens.values()) == 234 and len(contagens) == 15
    base = _base({"ugc": contagens}, n_perfis_base=26)

    custo = estimar_custo(Recorte(dias=90, teto=250), 26, HOJE, calibracao=base)

    assert custo["resultados_itens"]["ugc"] == 385
    assert custo["estimado_usd"]["ugc"] == pytest.approx(385 / 1000 * 2.3)
    assert custo["maximo_usd"]["ugc"] == pytest.approx(6500 / 1000 * 2.3)
    assert custo["base_calibracao"] == {"posts": SEM_BASE, "reels": SEM_BASE, "ugc": BASE}
    assert custo["estimado_usd"]["total"] < custo["maximo_usd"]["total"]


# --- quando a base não prevê nada: vale o máximo da coleção -------------------------------


def test_recorte_so_com_teto_deixa_posts_e_reels_sem_base_mas_calibra_o_ugc():
    base = _base({"posts": {"gov_a": 6}, "reels": {"gov_a": 6}, "ugc": {"gov_a": 4}}, n_perfis_base=1)
    custo = estimar_custo(Recorte(teto=50), 1, HOJE, calibracao=base)

    assert custo["resultados_itens"]["posts"] == custo["resultados_itens"]["reels"] == 50  # sem janela: máximo
    assert custo["resultados_itens"]["ugc"] == 4
    assert custo["base_calibracao"] == {"posts": SEM_BASE, "reels": SEM_BASE, "ugc": BASE}


def test_base_sem_janela_em_dias_deixa_posts_e_reels_sem_base():
    sem_janela = Calibracao(
        n_governadores=1,
        origem=BASE,
        dias_janela=None,
        base_teto=30,
        n_perfis_base=1,
        contagens={"posts": {"gov_a": 6}, "reels": {"gov_a": 6}, "ugc": {"gov_a": 4}},
    )
    custo = estimar_custo(Recorte(dias=30, teto=250), 1, HOJE, calibracao=sem_janela)

    assert custo["resultados_itens"]["posts"] == 250
    assert custo["base_calibracao"]["posts"] == SEM_BASE
    assert custo["base_calibracao"]["ugc"] == BASE


def test_base_zerada_na_colecao_vale_o_maximo_e_nunca_zero():
    base = _base({"posts": {"gov_a": 6}, "ugc": {}}, n_perfis_base=1)
    custo = estimar_custo(Recorte(dias=30, teto=250), 1, HOJE, calibracao=base)

    assert custo["resultados_itens"]["ugc"] == 250  # ninguém teve UGC na base: não prevê, vale o máximo
    assert custo["base_calibracao"]["ugc"] == SEM_BASE
    zerada = _base({"posts": {"gov_a": 0}}, n_perfis_base=1)
    assert estimar_custo(Recorte(dias=30, teto=250), 1, HOJE, calibracao=zerada)["resultados_itens"]["posts"] == 250


def test_sem_calibracao_com_motivo_vale_o_maximo():
    custo = estimar_custo(Recorte(dias=90, teto=250), 26, HOJE, calibracao=Calibracao.sem_calibracao("HF fora", 26))

    assert custo["estimado_usd"] == custo["maximo_usd"]
    assert set(custo["base_calibracao"].values()) == {SEM_BASE}


def test_estimado_nunca_passa_do_maximo_em_nenhum_recorte():
    base = _base({"posts": {"gov_a": 12, "gov_b": 1}, "reels": {"gov_a": 3}, "ugc": {"gov_b": 9}}, n_perfis_base=2)
    for recorte in (Recorte(dias=1, teto=10), Recorte(dias=30, teto=100), Recorte(dias=90), Recorte(teto=30)):
        custo = estimar_custo(recorte, 2, HOJE, calibracao=base)
        for chave in (*COLECOES, "total"):
            assert custo["estimado_usd"][chave] <= custo["maximo_usd"][chave] + 1e-9, (recorte, chave)


def test_resultado_tem_unidade_nas_chaves_e_so_numeros_texto_e_booleano():
    custo = estimar_custo(Recorte(dias=90, teto=250), 26, HOJE)

    assert set(custo) == {"estimado_usd", "maximo_usd", "resultados_itens", "teto", "base_calibracao"}
    for bloco in ("estimado_usd", "maximo_usd", "resultados_itens"):
        assert set(custo[bloco]) == {"perfis", "posts", "reels", "ugc", "total"}
        assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in custo[bloco].values())


# --- custo real e diferença ---------------------------------------------------------------


EXECUCOES = [
    {"colecao": "perfis", "usd": 0.0702, "itens": 26},
    {"colecao": "posts", "usd": 1.6227, "itens": 601},
    {"colecao": "reels", "usd": 1.3582, "itens": 522},
    {"colecao": "ugc", "usd": 0.6642, "itens": 246},
]


def test_agregar_custo_real_devolve_custo_usd_e_resultados_itens_por_colecao():
    real = agregar_custo_real(EXECUCOES)

    assert real == {
        "custo_usd": {"perfis": 0.0702, "posts": 1.6227, "reels": 1.3582, "ugc": 0.6642, "total": 3.7153},
        "resultados_itens": {"perfis": 26, "posts": 601, "reels": 522, "ugc": 246, "total": 1395},
    }


def test_agregar_custo_real_soma_o_actor_que_rodou_mais_de_uma_vez_e_nunca_soma_parcial():
    dobrado = agregar_custo_real([*EXECUCOES, {"colecao": "posts", "usd": 0.5, "itens": 10}])
    assert dobrado["custo_usd"]["posts"] == 2.1227 and dobrado["resultados_itens"]["posts"] == 611

    assert agregar_custo_real(None) is None
    assert agregar_custo_real([]) is None
    assert agregar_custo_real([*EXECUCOES[:2], {"colecao": "reels", "usd": None, "itens": 5}]) is None


def test_diferenca_e_so_percentual_real_menos_estimado_sobre_estimado():
    estimado = estimar_custo(Recorte(dias=5, teto=30), 26, date(2026, 10, 6), plano="FREE")
    real = agregar_custo_real(EXECUCOES)

    dif = diferenca_percentual(estimado, real)

    assert set(dif) == {"custo_pct", "resultados_pct"}
    for nome in dif:
        assert set(dif[nome]) == {"perfis", "posts", "reels", "ugc", "total"}
    # sem base: estimado = máximo (26 x 30 = 780 itens por coleção); UGC real 246
    assert dif["resultados_pct"]["ugc"] == round((246 - 780) / 780 * 100, 1) == -68.5
    assert dif["resultados_pct"]["perfis"] == 0.0
    assert dif["custo_pct"]["total"] == round(
        (3.7153 - estimado["estimado_usd"]["total"]) / estimado["estimado_usd"]["total"] * 100, 1
    )
    assert dif["custo_pct"]["total"] < 0  # gastou menos que o estimado: folga


def test_diferenca_sem_custo_real_nao_existe():
    assert diferenca_percentual(estimar_custo(Recorte(dias=5, teto=30), 26, HOJE), None) is None
