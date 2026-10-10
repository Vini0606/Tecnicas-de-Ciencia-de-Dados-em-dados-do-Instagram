"""`coletar()`: do Recorte ao Snapshot local, com Apify falsa (ADR 0039, issue #248).

Os testes passam pela interface única do módulo Coleta: nenhuma rede, nenhum custo."""

import json
from datetime import date, datetime, timezone

import pandas as pd
import pytest
from deltalake import DeltaTable

from src.coleta.coletar import ColetaNaoConfirmada, coletar
from src.coleta.recorte import Recorte

HOJE = date(2026, 10, 9)
AGORA = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
LINK = "https://www.instagram.com/gov_a/"


class _ScraperFalso:
    def __init__(self, posts=None, reels=None, mentions=None):
        self.chamadas = []
        self._posts = posts if posts is not None else [_post("p1", "2026-08-10T10:00:00.000Z")]
        self._reels = reels if reels is not None else [_reel("r1", "2026-08-12T10:00:00.000Z")]
        self._mentions = mentions if mentions is not None else []

    def scrape_profiles(self, links):
        self.chamadas.append(("profiles", None))
        return [
            {
                "id": "1",
                "username": "gov_a",
                "fullName": "Governador A",
                "inputUrl": LINK,
                "followersCount": 1000,
                "followsCount": 10,
                "postsCount": 50,
            }
        ]

    def scrape_posts(self, links, extra_run_input=None):
        self.chamadas.append(("posts", extra_run_input))
        return self._posts

    def scrape_reels(self, links, extra_run_input=None):
        self.chamadas.append(("reels", extra_run_input))
        return self._reels

    def scrape_mentions(self, links, extra_run_input=None):
        self.chamadas.append(("mentions", extra_run_input))
        return self._mentions


def _post(id_, ts):
    return {
        "id": id_,
        "ownerId": "1",
        "ownerUsername": "gov_a",
        "inputUrl": LINK,
        "timestamp": ts,
        "likesCount": 10,
        "commentsCount": 2,
        "caption": "legenda de teste",
    }


def _reel(id_, ts):
    return {
        **_post(id_, ts),
        "latestComments": [
            {"id": "c1", "text": "muito bom", "ownerUsername": "fulano", "timestamp": ts}
        ],
    }


def _governadores():
    return pd.DataFrame(
        {
            "Governador": ["Governador A"],
            "Unidade Federativa": ["XX"],
            "Partido": ["P"],
            "Link": [LINK],
        }
    )


def _coletar(tmp_path, recorte, scraper=None, confirmar=lambda custo: True, **kw):
    return coletar(
        recorte,
        tmp_path / "dados",
        scraper=scraper or _ScraperFalso(),
        links=[LINK],
        governor_usernames=["gov_a"],
        df_governadores=_governadores(),
        confirmar=confirmar,
        hoje=HOJE,
        agora=AGORA,
        run_id="run_teste",
        **kw,
    )


def test_recorte_e_scraper_falso_produzem_snapshot_com_bronze_silver_gold_e_manifesto(tmp_path):
    resultado = _coletar(tmp_path, Recorte(dias=90, teto=250))

    destino = tmp_path / "dados"
    assert resultado.tag == "coleta_2026-10-09_ultimos-90d_teto-250"
    for camada, tabela in [
        ("bronze", "instagram_profiles"),
        ("bronze", "instagram_posts"),
        ("bronze", "instagram_reels"),
        ("silver", "profiles_clean"),
        ("silver", "posts_clean"),
        ("silver", "reels_clean"),
        ("silver", "comments_clean"),
        ("silver", "governors_metadata"),
        ("gold", "governor_engagement"),
    ]:
        assert len(DeltaTable(str(destino / camada / tabela)).to_pandas()) >= 1, (camada, tabela)

    manifesto = json.loads((destino / "manifesto.json").read_text(encoding="utf-8"))
    assert manifesto["identidade"]["tag"] == resultado.tag
    assert manifesto["cobertura"]["posts"]["itens"] == 1
    assert manifesto["cobertura"]["reels"]["itens"] == 1


def test_a_janela_do_recorte_chega_a_apify_como_posts_mais_novos_que_n_dias(tmp_path):
    scraper = _ScraperFalso()
    _coletar(tmp_path, Recorte(dias=90), scraper)

    extras = {tipo: extra for tipo, extra in scraper.chamadas}
    assert extras["posts"] == {"onlyPostsNewerThan": "90 days"}
    assert extras["reels"] == {"onlyPostsNewerThan": "90 days"}
    assert extras["profiles"] is None


def test_sem_confirmacao_nenhuma_chamada_paga_e_nenhum_arquivo_sao_feitos(tmp_path):
    scraper = _ScraperFalso()
    custos = []

    def recusar(custo):
        custos.append(custo)
        return False

    with pytest.raises(ColetaNaoConfirmada):
        _coletar(tmp_path, Recorte(dias=90, teto=250), scraper, confirmar=recusar)

    assert scraper.chamadas == []
    assert not (tmp_path / "dados").exists()
    assert custos == [pytest.approx(1.45, abs=0.01)]  # 1 link, pior caso (37,82 / 26)


def test_intervalo_absoluto_descarta_localmente_o_que_esta_fora_do_fim(tmp_path):
    scraper = _ScraperFalso(
        posts=[
            _post("dentro", "2026-07-20T10:00:00.000Z"),
            _post("depois_do_fim", "2026-09-20T10:00:00.000Z"),
        ],
        reels=[_reel("r_dentro", "2026-07-21T10:00:00.000Z")],
    )
    recorte = Recorte(inicio=date(2026, 7, 1), fim=date(2026, 8, 31))

    resultado = _coletar(tmp_path, recorte, scraper)

    posts = DeltaTable(str(tmp_path / "dados" / "bronze" / "instagram_posts")).to_pandas()
    assert posts["id"].tolist() == ["dentro"]
    assert resultado.tag == "coleta_2026-10-09_de-2026-07-01_ate-2026-08-31"
    # a Apify foi pedida desde o início (100 dias até hoje), não só até o fim
    assert dict(scraper.chamadas)["posts"] == {"onlyPostsNewerThan": "100 days"}


def test_falha_de_ugc_nao_derruba_a_coleta(tmp_path):
    class _SemUgc(_ScraperFalso):
        def scrape_mentions(self, links, extra_run_input=None):
            raise RuntimeError("actor de UGC indisponivel")

    resultado = _coletar(tmp_path, Recorte(teto=10), _SemUgc())

    assert (tmp_path / "dados" / "manifesto.json").exists()
    assert resultado.manifesto["cobertura"]["ugc"]["itens"] == 0


def test_modelagem_opcional_recebe_as_tabelas_derivadas(tmp_path):
    recebido = {}
    _coletar(tmp_path, Recorte(teto=10), modelar=recebido.update)

    assert {"reels", "comments", "posts", "engagement"} <= set(recebido)
    assert len(recebido["engagement"]) >= 1
