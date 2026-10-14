"""Calibração por perfil da estimativa de custo com a Coleta vigente no HF (issue #299).

Sem rede: a Coleta anterior é montada nos testes e o HF é substituído."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.coleta import calibracao as cal
from src.coleta import hf
from src.coleta.calibracao import MIN_DIAS_CALIBRACAO, Calibracao, calibrar, carregar_calibracao
from src.coleta.custo import estimar_custo
from src.coleta.recorte import Recorte

HOJE = date(2026, 10, 13)
EXTRAIDO = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def _perfil(username: str, itens: int) -> dict:
    return {"username": username, "itens": itens, "mais_antiga": None, "mais_recente": None}


def _coleta(posts, reels=(), dias=90, teto=250) -> hf.ColetaListada:
    def fonte(perfis):
        return {"itens": sum(p["itens"] for p in perfis), "mais_antiga": None, "mais_recente": None, "por_perfil": list(perfis)}

    return hf.ColetaListada(
        coleta=f"coleta_2026-10-01_ultimos-{dias}d_teto-{teto}",
        commit="abc123",
        recorte=Recorte(dias=dias, teto=teto),
        cobertura={"posts": fonte(posts), "reels": fonte(reels), "perfis": fonte([]), "ugc": fonte([])},
        extraido_em=EXTRAIDO,
    )


# --- calibração por perfil ---------------------------------------------------------------


def test_taxa_por_perfil_e_itens_divididos_pelos_dias_da_janela():
    c = calibrar(
        _coleta([_perfil("gov_a", 180), _perfil("gov_b", 90)], [_perfil("gov_a", 45)]),
        ["gov_a", "gov_b"],
    )

    assert not c.usa_taxas_fixas
    assert c.taxas["posts"] == {"gov_a": 2.0, "gov_b": 1.0}
    assert c.taxas["reels"] == {"gov_a": 0.5}
    assert c.taxa_media == {"posts": 1.5, "reels": 0.5}
    assert c.origem == "coleta_2026-10-01_ultimos-90d_teto-250"
    assert c.dias_janela == 90


def test_perfis_que_nao_sao_governadores_sao_ignorados():
    c = calibrar(_coleta([_perfil("gov_a", 90), _perfil("autor_de_ugc", 900)]), ["gov_a"])

    assert c.taxas["posts"] == {"gov_a": 1.0}
    assert c.perfis_calibrados == 1


def test_governador_ausente_na_coleta_anterior_usa_a_media_dos_calibrados():
    c = calibrar(_coleta([_perfil("gov_a", 180), _perfil("gov_b", 90)]), ["gov_a", "gov_b", "gov_c"])
    custo = estimar_custo(Recorte(dias=90, teto=250), 3, HOJE, calibracao=c)

    # gov_a 2,0 x 90 = 180; gov_b 1,0 x 90 = 90; gov_c pela média 1,5 x 90 = 135
    assert custo["resultados_posts"] == pytest.approx(405)


def test_o_teto_so_limita_os_perfis_que_o_atingem():
    c = calibrar(_coleta([_perfil("gov_a", 900), _perfil("gov_b", 90)], teto=1000), ["gov_a", "gov_b"])
    custo = estimar_custo(Recorte(dias=90, teto=250), 2, HOJE, calibracao=c)

    # gov_a: 10/dia x 90 = 900 -> teto 250; gov_b: 1/dia x 90 = 90
    assert custo["resultados_posts"] == pytest.approx(340)


def test_perfil_no_teto_da_coleta_anterior_e_sinalizado_como_taxa_minima():
    c = calibrar(_coleta([_perfil("gov_a", 250), _perfil("gov_b", 10)], teto=250), ["gov_a", "gov_b"])

    assert c.perfis_truncados == 1
    assert "no teto" in c.detalhe()


# --- quando a Coleta anterior não serve --------------------------------------------------


@pytest.mark.parametrize(
    ("coleta", "trecho"),
    [
        (None, "nenhuma Coleta"),
        (_coleta([_perfil("gov_a", 30)], dias=5, teto=30), "curta demais"),
        (_coleta([_perfil("outro", 30)]), "nenhum governador"),
    ],
)
def test_fallback_para_as_taxas_fixas_diz_o_motivo(coleta, trecho):
    c = calibrar(coleta, ["gov_a"])

    assert c.usa_taxas_fixas
    assert trecho in c.motivo_fallback
    assert trecho in c.detalhe()


def test_janela_minima_e_de_30_dias():
    assert MIN_DIAS_CALIBRACAO == 30
    assert calibrar(_coleta([_perfil("gov_a", 30)], dias=30), ["gov_a"]).usa_taxas_fixas is False
    assert calibrar(_coleta([_perfil("gov_a", 29)], dias=29), ["gov_a"]).usa_taxas_fixas is True


def test_coleta_anterior_so_com_teto_nao_tem_janela_e_cai_nas_taxas_fixas():
    coleta = _coleta([_perfil("gov_a", 30)])
    coleta = hf.ColetaListada(**{**coleta.__dict__, "recorte": Recorte(teto=30)})

    assert "sem janela" in calibrar(coleta, ["gov_a"]).motivo_fallback


# --- a estimativa com e sem calibração ---------------------------------------------------


def test_fallback_e_sem_calibracao_dao_a_mesma_estimativa_de_hoje():
    recorte = Recorte(dias=90, teto=250)
    sem = estimar_custo(recorte, 26, HOJE)

    assert estimar_custo(recorte, 26, HOJE, calibracao=None) == sem
    assert estimar_custo(recorte, 26, HOJE, calibracao=calibrar(None, ["gov_a"])) == sem


def test_o_pior_caso_nao_depende_da_calibracao():
    recorte = Recorte(dias=90, teto=250)
    c = calibrar(_coleta([_perfil("gov_a", 90)]), ["gov_a"])
    com, sem = estimar_custo(recorte, 1, HOJE, calibracao=c), estimar_custo(recorte, 1, HOJE)

    assert com["total"] < sem["total"]  # gov_a publica pouco: esperado menor
    for chave in ("pior_caso_posts", "pior_caso_reels", "pior_caso_ugc", "pior_caso_total"):
        assert com[chave] == sem[chave]


def test_calibracao_nao_afeta_recorte_so_com_teto():
    c = calibrar(_coleta([_perfil("gov_a", 90)]), ["gov_a"])

    assert estimar_custo(Recorte(teto=10), 1, HOJE, calibracao=c) == estimar_custo(Recorte(teto=10), 1, HOJE)


# --- leitura do HF -----------------------------------------------------------------------


def test_carregar_calibracao_usa_a_coleta_mais_recente_do_hf(monkeypatch):
    antiga = _coleta([_perfil("gov_a", 9)])
    recente = _coleta([_perfil("gov_a", 180)])
    monkeypatch.setattr(hf, "listar", lambda *, cliente: [recente, antiga])  # da mais recente para a mais antiga

    c = carregar_calibracao(lambda: object(), ["gov_a"])

    assert c.taxas["posts"] == {"gov_a": 2.0}


def test_hf_indisponivel_vira_fallback_com_motivo_sem_levantar(monkeypatch):
    def quebra():
        raise hf.ErroColetaHF("sem token")

    c = carregar_calibracao(quebra, ["gov_a"])

    assert c.usa_taxas_fixas and "HF indisponivel" in c.motivo_fallback

    monkeypatch.setattr(hf, "listar", lambda *, cliente: (_ for _ in ()).throw(OSError("sem rede")))
    assert "HF indisponivel" in carregar_calibracao(lambda: object(), ["gov_a"]).motivo_fallback


def test_calibracao_e_imutavel_e_descreve_a_origem():
    c = calibrar(_coleta([_perfil("gov_a", 180)]), ["gov_a"])

    assert isinstance(c, Calibracao)
    assert c.resumo() == "coleta_2026-10-01_ultimos-90d_teto-250"
    assert "1/1 governadores com taxa propria" in c.detalhe()
    with pytest.raises(AttributeError):
        c.origem = "outra"  # type: ignore[misc]


def test_modulo_expoe_as_constantes_nomeadas():
    assert cal.MIN_DIAS_CALIBRACAO == 30
