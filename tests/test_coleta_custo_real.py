"""Custo real por actor no manifesto e comparação com a estimativa (issue #297).

Tudo com Apify falsa: nenhuma rede, nenhum custo."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from test_coleta_coletar import LINK, _coletar, _governadores, _ScraperFalso
from test_coleta_manifesto import _gerar, snapshot  # noqa: F401  (fixture)

from src.coleta import cli, hf
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
        "perfis": 0.07, "posts": 0.70, "reels": 0.40, "ugc": 0.25, "total": 1.42,
        "resultados_perfis": 26, "resultados_posts": 270, "resultados_reels": 154, "resultados_ugc": 93,
    }
    assert resultado.custo_real == pytest.approx(esperado)
    gravado = json.loads((tmp_path / "dados" / "manifesto.json").read_text(encoding="utf-8"))
    assert gravado["custo"]["real"] == pytest.approx(esperado)


def test_chaves_de_custo_real_e_estimado_sao_comparaveis(tmp_path):
    resultado = _coletar(tmp_path, Recorte(dias=90, teto=250), _ScraperComCusto(EXECUCOES))

    comuns = {"perfis", "posts", "reels", "ugc", "total"}
    assert comuns <= set(resultado.custo_real)
    assert comuns <= set(resultado.manifesto["custo"]["estimado"])


def test_sem_registro_de_execucoes_o_custo_real_fica_nulo(tmp_path):
    resultado = _coletar(tmp_path, Recorte(dias=90, teto=250))  # _ScraperFalso não registra nada

    assert resultado.custo_real is None
    assert resultado.manifesto["custo"]["real"] is None


def test_custo_real_nunca_e_parcial_quando_uma_chamada_vem_sem_custo(tmp_path, caplog):
    execucoes = [*EXECUCOES[:2], {"colecao": "reels", "usd": None, "itens": 154}]
    with caplog.at_level("WARNING"):
        resultado = _coletar(tmp_path, Recorte(dias=90, teto=250), _ScraperComCusto(execucoes))

    assert resultado.custo_real is None
    assert resultado.manifesto["custo"]["real"] is None
    assert "custo real" in caplog.text.lower()


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


def test_custo_real_aceita_nulo_numero_antigo_e_dicionario_de_numeros(snapshot):  # noqa: F811
    m = _gerar(snapshot)
    for real in (None, 1.8, {"posts": 0.7, "total": 1.4, "resultados_posts": 270}):
        m["custo"]["real"] = real
        validar_manifesto(m)

    for ruim in ({"posts": "caro"}, {"posts": True}, {1: 0.5}, "1,8", [0.5]):
        m["custo"]["real"] = ruim
        with pytest.raises(ValueError, match="custo.real"):
            validar_manifesto(m)


# --- CLI ----------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _sem_rede_no_hf(monkeypatch):
    """A calibração consulta o HF; nos testes ele nunca é tocado (cai nas taxas fixas)."""

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
    # colunas: coleção, estimado, real, diferença (US$), diferença (%) -- vírgula decimal
    assert comparacao["Posts"][2] == "0,70"
    assert comparacao["Total"][2] == "1,42"
    assert comparacao["Total"][3].startswith("-")  # real abaixo do estimado (1 governador: US$ 1,73)
    assert comparacao["Total"][4].endswith("%")


def test_com_yes_sem_custo_real_avisa_que_nao_foi_possivel_ler(tmp_path, capsys, _governadores_falsos):
    cli.main(
        ["coletar", "--dias", "90", "--teto", "250", "--destino", str(tmp_path / "dados"), "--yes"],
        scraper_factory=lambda recorte, hoje: _ScraperFalso(),
        agora=AGORA,
    )
    saida = capsys.readouterr().out

    assert "CUSTO ESTIMADO x REAL" not in saida
    assert "Custo real indisponivel" in saida
