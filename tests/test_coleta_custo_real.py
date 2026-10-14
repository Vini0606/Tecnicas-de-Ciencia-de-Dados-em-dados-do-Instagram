"""Custo real por actor no manifesto e comparação com a estimativa (issue #297).

Tudo com Apify falsa: nenhuma rede, nenhum custo."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest
from test_coleta_coletar import LINK, _coletar, _governadores, _ScraperFalso
from test_coleta_manifesto import _gerar, snapshot  # noqa: F401  (fixture)

from src.coleta import cli, hf
from src.coleta.custo import agregar_custo_real, estimar_custo
from src.coleta.manifesto import validar_manifesto
from src.coleta.recorte import Recorte
from src.data_extract.scraper import InstagramScraper

AGORA = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


class _ScraperComCusto(_ScraperFalso):
    """Scraper falso que, como o real, registra o custo de cada chamada paga."""

    def __init__(self, execucoes, **kw):
        super().__init__(**kw)
        self.execucoes = execucoes


EXECUCOES = [
    {"colecao": "perfis", "usd": 0.07, "itens": 26},
    {"colecao": "posts", "usd": 0.60, "itens": 230},
    {"colecao": "posts", "usd": 0.10, "itens": 40},  # mesma coleção rodada duas vezes: soma
    {"colecao": "reels", "usd": 0.40, "itens": 154},
    {"colecao": "ugc", "usd": 0.25, "itens": 93},
]


# --- seam principal: a Coleta de ponta a ponta -----------------------------------------


def test_custo_real_por_actor_vai_para_o_manifesto_e_para_o_resultado(tmp_path):
    resultado = _coletar(tmp_path, Recorte(dias=90, teto=250), _ScraperComCusto(EXECUCOES))

    esperado = {
        "custo_usd": {"perfis": 0.07, "posts": 0.70, "reels": 0.40, "ugc": 0.25, "total": 1.42},
        "resultados_itens": {"perfis": 26, "posts": 270, "reels": 154, "ugc": 93, "total": 543},
    }
    gravado = json.loads((tmp_path / "dados" / "manifesto.json").read_text(encoding="utf-8"))
    assert gravado["versao_esquema"] == 4
    for real in (resultado.custo_real, gravado["custo"]["real"]):
        assert real["custo_usd"] == pytest.approx(esperado["custo_usd"])
        assert real["resultados_itens"] == esperado["resultados_itens"]


def test_manifesto_traz_estimado_real_e_diferenca_percentual_sem_nulos(tmp_path):
    resultado = _coletar(tmp_path, Recorte(dias=90, teto=250), _ScraperComCusto(EXECUCOES))

    custo = resultado.manifesto["custo"]
    assert set(custo) == {"estimado", "real", "diferenca"}
    assert set(custo["diferenca"]) == {"custo_pct", "resultados_pct"}
    # 1 governador falso, sem base: estimado = maximo = 250 itens; posts reais 270 => +8,0%
    assert custo["estimado"]["resultados_itens"]["posts"] == 250
    assert custo["diferenca"]["resultados_pct"]["posts"] == 8.0
    assert custo["diferenca"]["custo_pct"]["total"] == round(
        (1.42 - custo["estimado"]["estimado_usd"]["total"]) / custo["estimado"]["estimado_usd"]["total"] * 100, 1
    )
    assert custo["estimado"]["teto"] == {"aplicado_itens_por_perfil": 250, "padrao": False}


def test_chaves_de_custo_real_e_estimado_sao_comparaveis(tmp_path):
    resultado = _coletar(tmp_path, Recorte(dias=90, teto=250), _ScraperComCusto(EXECUCOES))

    estimado = resultado.manifesto["custo"]["estimado"]
    assert set(resultado.custo_real["custo_usd"]) == set(estimado["estimado_usd"]) == set(estimado["maximo_usd"])
    assert set(resultado.custo_real["resultados_itens"]) == set(estimado["resultados_itens"])


def test_sem_registro_de_execucoes_nao_ha_custo_real_nem_diferenca_no_manifesto(tmp_path):
    resultado = _coletar(tmp_path, Recorte(dias=90, teto=250))  # _ScraperFalso não registra nada

    assert resultado.custo_real is None
    assert set(resultado.manifesto["custo"]) == {"estimado"}  # nunca null: os blocos que faltam são omitidos


def test_custo_real_nunca_e_parcial_quando_uma_chamada_vem_sem_custo(tmp_path, caplog):
    execucoes = [*EXECUCOES[:2], {"colecao": "reels", "usd": None, "itens": 154}]
    with caplog.at_level("WARNING"):
        resultado = _coletar(tmp_path, Recorte(dias=90, teto=250), _ScraperComCusto(execucoes))

    assert resultado.custo_real is None
    assert "real" not in resultado.manifesto["custo"] and "diferenca" not in resultado.manifesto["custo"]
    assert "custo real" in caplog.text.lower()


def test_custo_real_acima_do_maximo_gera_aviso(tmp_path, caplog):
    caro = [{"colecao": "posts", "usd": 5.0, "itens": 10}, *[{"colecao": c, "usd": 0.1, "itens": 1} for c in ("perfis", "reels", "ugc")]]
    with caplog.at_level("WARNING"):
        _coletar(tmp_path, Recorte(dias=90, teto=250), _ScraperComCusto(caro))

    assert "acima do custo maximo" in caplog.text


# --- seam secundário: o scraper com cliente Apify falso --------------------------------


def _client(final, itens=()):
    client = MagicMock()
    client.actor.return_value.call.return_value = {"id": "run1", "defaultDatasetId": "d1"}
    client.dataset.return_value.iterate_items.side_effect = lambda: iter(list(itens))
    client.run.return_value.get.return_value = final
    return client


def test_scraper_registra_colecao_custo_da_execucao_finalizada_e_itens():
    client = _client({"usageTotalUsd": 0.621}, [{"id": "1"}, {"id": "2"}])
    scraper = InstagramScraper(client)

    scraper.scrape_posts(["gov"])

    assert scraper.execucoes == [{"colecao": "posts", "usd": 0.621, "itens": 2}]
    client.run.assert_called_with("run1")  # custo lido da execução finalizada


def test_cada_metodo_do_scraper_tem_sua_colecao():
    scraper = InstagramScraper(_client({"usageTotalUsd": 0.1}))

    scraper.scrape_profiles(["l"])
    scraper.scrape_posts(["l"])
    scraper.scrape_reels(["l"])
    scraper.scrape_mentions(["l"])

    assert [e["colecao"] for e in scraper.execucoes] == ["perfis", "posts", "reels", "ugc"]


def test_custo_ilegivel_vira_none_sem_quebrar_a_extracao():
    client = _client(None, [{"id": "1"}])
    client.run.return_value.get.side_effect = RuntimeError("falha de rede")
    scraper = InstagramScraper(client)

    assert scraper.scrape_posts(["gov"]) == [{"id": "1"}]
    assert scraper.execucoes == [{"colecao": "posts", "usd": None, "itens": 1}]


@pytest.mark.parametrize("final", [{"usageTotalUsd": None}, {"usageTotalUsd": "caro"}, {}, None])
def test_custo_que_nao_e_numero_vira_none(final):
    scraper = InstagramScraper(_client(final))

    scraper.scrape_reels(["gov"])

    assert scraper.execucoes[0]["usd"] is None


# --- manifesto ----------------------------------------------------------------------------


def _v4(snapshot):  # noqa: F811
    return _gerar(
        snapshot,
        custo_estimado=estimar_custo(Recorte(dias=90, teto=250), 26, date(2026, 10, 9)),
        custo_real=agregar_custo_real(EXECUCOES_CHEIAS),
    )


EXECUCOES_CHEIAS = [
    {"colecao": "perfis", "usd": 0.07, "itens": 26},
    {"colecao": "posts", "usd": 0.70, "itens": 270},
    {"colecao": "reels", "usd": 0.40, "itens": 154},
    {"colecao": "ugc", "usd": 0.25, "itens": 93},
]


def test_manifesto_v4_valido_com_estimado_real_e_diferenca(snapshot):  # noqa: F811
    m = _v4(snapshot)

    validar_manifesto(m)
    assert m["versao_esquema"] == 4


def test_custo_real_e_diferenca_podem_faltar_mas_nunca_ser_nulos(snapshot):  # noqa: F811
    m = _v4(snapshot)
    nulo = json.loads(json.dumps(m))
    nulo["custo"]["real"] = None  # com a diferenca presente: o bloco existe, mas vazio
    with pytest.raises(ValueError, match="custo.real"):
        validar_manifesto(nulo)

    del m["custo"]["real"], m["custo"]["diferenca"]
    validar_manifesto(m)  # só o estimado


def test_diferenca_exige_estimado_e_real(snapshot):  # noqa: F811
    m = _v4(snapshot)
    del m["custo"]["real"]
    with pytest.raises(ValueError, match="diferenca exige"):
        validar_manifesto(m)


def test_custo_real_v4_recusa_formato_ruim(snapshot):  # noqa: F811
    for ruim in ({"posts": "caro"}, {"custo_usd": {"posts": True}}, 1.8, [0.5], {"custo_usd": {}, "resultados_itens": {}}):
        m = _v4(snapshot)
        m["custo"]["real"] = ruim
        with pytest.raises(ValueError, match="custo.real"):
            validar_manifesto(m)


# --- CLI ----------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _sem_rede_no_hf(monkeypatch):
    """A calibração consulta o HF; nos testes ele nunca é tocado (sem base: estimado = máximo)."""

    def sem_hf(*_a, **_k):
        raise hf.ErroColetaHF("HF bloqueado nos testes")

    monkeypatch.setattr(hf, "ClienteColetaHFReal", sem_hf)


@pytest.fixture
def _governadores_falsos(monkeypatch):
    monkeypatch.setattr(cli, "_carregar_governadores", lambda: ([LINK], ["gov_a"], _governadores()))


def _linhas_da_tabela(saida: str) -> dict[str, list[str]]:
    return {
        linha.split()[0]: linha.split()
        for linha in saida.splitlines()
        if linha.split()[:1] in (["Posts"], ["Reels"], ["UGC"], ["Perfis"], ["Total"])
    }


def test_com_yes_mostra_a_comparacao_entre_custo_estimado_e_real(tmp_path, capsys, _governadores_falsos):
    cli.main(
        ["coletar", "--dias", "90", "--teto", "250", "--destino", str(tmp_path / "dados"), "--yes"],
        scraper_factory=lambda recorte, hoje: _ScraperComCusto(EXECUCOES),
        agora=AGORA,
    )
    saida = capsys.readouterr().out

    assert "CUSTO ESTIMADO x REAL" in saida
    comparacao = _linhas_da_tabela(saida.split("CUSTO ESTIMADO x REAL")[1])
    # colunas: coleção, estimado (US$), real (US$), diferença (%), itens estimados / reais -- vírgula decimal
    assert comparacao["Posts"][2] == "0,70"
    assert comparacao["Total"][2] == "1,42"
    assert comparacao["Total"][3].startswith("-")  # real abaixo do estimado (1 governador: US$ 1,73)
    assert comparacao["Total"][3].endswith("%")
    assert comparacao["Total"][-3:] == [comparacao["Total"][-3], "/", "543"]  # itens reais


def test_com_yes_sem_custo_real_avisa_que_nao_foi_possivel_ler(tmp_path, capsys, _governadores_falsos):
    cli.main(
        ["coletar", "--dias", "90", "--teto", "250", "--destino", str(tmp_path / "dados"), "--yes"],
        scraper_factory=lambda recorte, hoje: _ScraperFalso(),
        agora=AGORA,
    )
    saida = capsys.readouterr().out

    assert "CUSTO ESTIMADO x REAL" not in saida
    assert "Custo real indisponivel" in saida
    manifesto = json.loads((tmp_path / "dados" / "manifesto.json").read_text(encoding="utf-8"))
    assert set(manifesto["custo"]) == {"estimado"}


def _run_com_eventos(usd, contagens, precos):
    return {
        "usageTotalUsd": usd,
        "chargedEventCounts": contagens,
        "pricingInfo": {
            "pricingModel": "PAY_PER_EVENT",
            "pricingPerEvent": {"actorChargeEvents": {k: {"eventPriceUsd": v} for k, v in precos.items()}},
        },
    }


def test_sem_usage_total_o_custo_sai_dos_eventos_cobrados_e_seus_precos():
    # run real de posts do piloto: 601 x (post 0.0017 + post-details 0.001) = 1.6227
    final = _run_com_eventos(None, {"post": 601, "post-details": 601}, {"post": 0.0017, "post-details": 0.001})
    scraper = InstagramScraper(_client(final, [{"id": "1"}]))

    scraper.scrape_posts(["gov"])

    assert scraper.execucoes[0]["usd"] == pytest.approx(1.6227)


def test_usage_total_tem_prioridade_sobre_o_calculo_por_eventos():
    final = _run_com_eventos(0.5, {"post": 10}, {"post": 0.0017})
    scraper = InstagramScraper(_client(final))

    scraper.scrape_posts(["gov"])

    assert scraper.execucoes[0]["usd"] == 0.5


def test_evento_cobrado_sem_preco_conhecido_nao_gera_custo_parcial():
    final = _run_com_eventos(None, {"post": 10, "transcript": 3}, {"post": 0.0017})
    scraper = InstagramScraper(_client(final))

    scraper.scrape_posts(["gov"])

    assert scraper.execucoes[0]["usd"] is None
