"""Custo real nunca é soma parcial quando uma chamada paga falha (issue #297, revisão)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from test_coleta_coletar import _coletar, _ScraperFalso

from src.coleta.recorte import Recorte
from src.data_extract.scraper import InstagramScraper


def _client_que_falha_no_actor():
    client = MagicMock()
    client.actor.return_value.call.side_effect = RuntimeError("actor caiu")
    return client


def test_chamada_que_falha_e_registrada_com_custo_ilegivel_e_a_excecao_sobe():
    scraper = InstagramScraper(_client_que_falha_no_actor())

    with pytest.raises(RuntimeError, match="actor caiu"):
        scraper.scrape_mentions(["gov"])

    assert scraper.execucoes == [{"colecao": "ugc", "usd": None, "itens": 0}]


class _ScraperComUgcQueFalha(_ScraperFalso):
    """Como o real: o UGC gasta, falha e a ingestão tolera (a Coleta segue sem UGC)."""

    def __init__(self):
        super().__init__()
        self.execucoes = [
            {"colecao": "perfis", "usd": 0.07, "itens": 1},
            {"colecao": "posts", "usd": 0.60, "itens": 1},
            {"colecao": "reels", "usd": 0.40, "itens": 1},
        ]

    def scrape_mentions(self, links, extra_run_input=None):
        self.execucoes.append({"colecao": "ugc", "usd": None, "itens": 0})
        raise RuntimeError("UGC caiu")


def test_ugc_que_falha_nao_vira_total_parcial_no_manifesto(tmp_path):
    resultado = _coletar(tmp_path, Recorte(dias=90, teto=250), _ScraperComUgcQueFalha())

    assert resultado.custo_real is None
    assert resultado.manifesto["custo"]["real"] is None
