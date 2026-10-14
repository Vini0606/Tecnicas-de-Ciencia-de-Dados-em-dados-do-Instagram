"""Base de calibração da estimativa de custo com a Coleta vigente no HF (issue #299, ADR 0042).

Sem rede: a Coleta anterior é montada nos testes e o HF é substituído."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.coleta import hf
from src.coleta.calibracao import Calibracao, calibrar, carregar_calibracao
from src.coleta.custo import SEM_BASE, estimar_custo
from src.coleta.recorte import Recorte

HOJE = date(2026, 10, 13)
EXTRAIDO = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def _perfil(username: str, itens: int) -> dict:
    return {"username": username, "itens": itens, "mais_antiga": None, "mais_recente": None}


def _coleta(posts, reels=(), ugc=(), dias=90, teto=250, n_perfis=None, recorte=None) -> hf.ColetaListada:
    def fonte(perfis, itens=None):
        total = sum(p["itens"] for p in perfis) if itens is None else itens
        return {"itens": total, "mais_antiga": None, "mais_recente": None, "por_perfil": list(perfis)}

    usernames = {p["username"] for p in (*posts, *reels, *ugc)}
    return hf.ColetaListada(
        coleta=f"coleta_2026-10-01_ultimos-{dias}d_teto-{teto}",
        commit="abc123",
        recorte=recorte or Recorte(dias=dias, teto=teto),
        cobertura={
            "posts": fonte(posts),
            "reels": fonte(reels),
            "perfis": fonte([], itens=n_perfis if n_perfis is not None else max(len(usernames), 1)),
            "ugc": fonte(ugc),
        },
        extraido_em=EXTRAIDO,
    )


# --- contagem por governador -------------------------------------------------------------


def test_contagem_por_governador_e_coleta_vem_da_cobertura_da_coleta_anterior():
    c = calibrar(
        _coleta([_perfil("gov_a", 180), _perfil("gov_b", 90)], [_perfil("gov_a", 45)], [_perfil("gov_b", 7)]),
        ["gov_a", "gov_b"],
    )

    assert not c.usa_sem_base
    assert c.contagens["posts"] == {"gov_a": 180, "gov_b": 90}
    assert c.contagens["reels"] == {"gov_a": 45}
    assert c.contagens["ugc"] == {"gov_b": 7}
    assert c.origem == "coleta_2026-10-01_ultimos-90d_teto-250"
    assert (c.dias_janela, c.base_teto, c.n_perfis_base) == (90, 250, 2)
    assert c.perfis_calibrados == 2


def test_perfis_que_nao_sao_governadores_sao_ignorados():
    c = calibrar(_coleta([_perfil("gov_a", 90), _perfil("autor_de_ugc", 900)]), ["gov_a"])

    assert c.contagens["posts"] == {"gov_a": 90}
    assert c.perfis_calibrados == 1


def test_usernames_do_manifesto_e_do_elenco_casam_sem_diferenca_de_caixa():
    c = calibrar(_coleta([_perfil("Gov_A", 90)]), ["gov_A"])

    assert c.contagens["posts"] == {"gov_a": 90}


def test_base_curta_e_usada_por_menor_que_seja_a_janela():
    c = calibrar(_coleta([_perfil("gov_a", 30)], dias=5, teto=30), ["gov_a"])

    assert not c.usa_sem_base
    assert c.dias_janela == 5 and c.base_teto == 30


def test_coleta_anterior_so_com_teto_nao_tem_janela_mas_ainda_serve_de_base():
    c = calibrar(_coleta([_perfil("gov_a", 30)], ugc=[_perfil("gov_a", 4)], recorte=Recorte(teto=30)), ["gov_a"])

    assert not c.usa_sem_base
    assert c.dias_janela is None  # posts e reels ficam sem base na projeção; o UGC não depende da janela
    assert c.contagens["ugc"] == {"gov_a": 4}


def test_janela_de_um_dia_so_nao_vira_dias_da_base():
    um_dia = Recorte(inicio=date(2026, 9, 30), fim=date(2026, 9, 30))

    assert calibrar(_coleta([_perfil("gov_a", 3)], recorte=um_dia), ["gov_a"]).dias_janela is None


def test_perfil_no_teto_da_coleta_anterior_e_sinalizado_como_censurado():
    c = calibrar(_coleta([_perfil("gov_a", 250), _perfil("gov_b", 10)], teto=250), ["gov_a", "gov_b"])

    assert c.perfis_truncados == 1
    assert "no teto" in c.detalhe()


def test_perfil_no_teto_padrao_da_coleta_de_origem_tambem_e_sinalizado():
    # Coleta anterior sem --teto: vale o teto padrão max(200, 7 x 90) = 630 por perfil
    coleta = _coleta([_perfil("gov_a", 630), _perfil("gov_b", 50)], recorte=Recorte(dias=90))
    c = calibrar(coleta, ["gov_a", "gov_b"])

    assert c.perfis_truncados == 1 and c.base_teto == 630


# --- quando não há base ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("coleta", "trecho"),
    [
        (None, "nenhuma Coleta"),
        (_coleta([_perfil("outro", 30)]), "nenhum governador"),
    ],
)
def test_sem_base_diz_o_motivo(coleta, trecho):
    c = calibrar(coleta, ["gov_a"])

    assert c.usa_sem_base
    assert trecho in c.motivo_fallback
    assert trecho in c.detalhe()
    assert "sem base" in c.resumo()


def test_sem_calibracao_constroi_a_ausencia_de_base_com_motivo():
    c = Calibracao.sem_calibracao("desligada", 26)

    assert c.usa_sem_base and c.detalhe() == "desligada" and c.n_governadores == 26
    assert c.contagens == {"posts": {}, "reels": {}, "ugc": {}}


# --- a estimativa com e sem base ---------------------------------------------------------


def test_sem_base_e_sem_calibracao_dao_a_mesma_estimativa_o_maximo():
    recorte = Recorte(dias=90, teto=250)
    sem = estimar_custo(recorte, 26, HOJE)

    assert estimar_custo(recorte, 26, HOJE, calibracao=None) == sem
    assert estimar_custo(recorte, 26, HOJE, calibracao=calibrar(None, ["gov_a"])) == sem
    assert sem["estimado_usd"] == sem["maximo_usd"]


def test_calibrar_e_estimar_de_ponta_a_ponta_com_base_de_5_dias():
    # gov_a 10 posts em 5 dias, gov_b sem itens (a base leu 2 perfis)
    c = calibrar(_coleta([_perfil("gov_a", 10)], dias=5, teto=30, n_perfis=2), ["gov_a", "gov_b"])
    custo = estimar_custo(Recorte(dias=30, teto=250), 2, HOJE, calibracao=c)

    assert custo["resultados_itens"]["posts"] == 188  # ceil(60 + 3 x sqrt(2) x 30)
    assert custo["base_calibracao"]["posts"] == "coleta_2026-10-01_ultimos-5d_teto-30"
    assert custo["base_calibracao"]["reels"] == SEM_BASE  # a base não tem reels


def test_o_maximo_nao_depende_da_calibracao():
    recorte = Recorte(dias=90, teto=250)
    c = calibrar(_coleta([_perfil("gov_a", 90)]), ["gov_a"])
    com, sem = estimar_custo(recorte, 1, HOJE, calibracao=c), estimar_custo(recorte, 1, HOJE)

    assert com["estimado_usd"]["total"] < sem["estimado_usd"]["total"]  # gov_a publica pouco: estimado menor
    assert com["maximo_usd"] == sem["maximo_usd"]
    assert com["resultados_itens"]["posts"] == 90  # 90 / 90 dias x 90 dias, sem desvio com um governador


def test_calibracao_so_afeta_o_ugc_num_recorte_so_com_teto():
    c = calibrar(_coleta([_perfil("gov_a", 90)], ugc=[_perfil("gov_a", 4)]), ["gov_a"])
    custo = estimar_custo(Recorte(teto=10), 1, HOJE, calibracao=c)

    assert custo["resultados_itens"] == {"perfis": 1, "posts": 10, "reels": 10, "ugc": 4, "total": 25}


# --- leitura do HF -----------------------------------------------------------------------


def test_carregar_calibracao_usa_a_coleta_mais_recente_do_hf(monkeypatch):
    antiga = _coleta([_perfil("gov_a", 9)])
    recente = _coleta([_perfil("gov_a", 180)])
    monkeypatch.setattr(hf, "listar", lambda *, cliente: [recente, antiga])  # da mais recente para a mais antiga

    c = carregar_calibracao(lambda: object(), ["gov_a"])

    assert c.contagens["posts"] == {"gov_a": 180}


def test_hf_indisponivel_vira_sem_base_com_motivo_sem_levantar(monkeypatch):
    def quebra():
        raise hf.ErroColetaHF("sem token")

    c = carregar_calibracao(quebra, ["gov_a"])

    assert c.usa_sem_base and "HF indisponivel" in c.motivo_fallback

    monkeypatch.setattr(hf, "listar", lambda *, cliente: (_ for _ in ()).throw(OSError("sem rede")))
    assert "HF indisponivel" in carregar_calibracao(lambda: object(), ["gov_a"]).motivo_fallback


def test_sem_nenhuma_coleta_no_hf_vira_sem_base(monkeypatch):
    monkeypatch.setattr(hf, "listar", lambda *, cliente: [])

    assert "nenhuma Coleta" in carregar_calibracao(lambda: object(), ["gov_a"]).motivo_fallback


def test_cobertura_fora_do_formato_vira_sem_base_sem_quebrar_a_estimativa(monkeypatch):
    quebrada = _coleta([_perfil("gov_a", 1)])
    del quebrada.cobertura["posts"]["por_perfil"][0]["itens"]  # manifesto fora do formato
    monkeypatch.setattr(hf, "listar", lambda *, cliente: [quebrada])

    c = carregar_calibracao(lambda: object(), ["gov_a"])

    assert c.usa_sem_base and "ilegivel" in c.motivo_fallback


def test_calibracao_e_imutavel_e_descreve_a_origem():
    c = calibrar(_coleta([_perfil("gov_a", 180)]), ["gov_a"])

    assert isinstance(c, Calibracao)
    assert c.resumo() == "coleta_2026-10-01_ultimos-90d_teto-250"
    assert "90 dias; 1/1 governadores com itens na base" in c.detalhe()
    with pytest.raises(AttributeError):
        c.origem = "outra"  # type: ignore[misc]


def test_detalhe_de_base_sem_janela_avisa_que_posts_e_reels_ficam_sem_base():
    c = calibrar(_coleta([_perfil("gov_a", 30)], recorte=Recorte(teto=30)), ["gov_a"])

    assert "sem janela em dias" in c.detalhe()
