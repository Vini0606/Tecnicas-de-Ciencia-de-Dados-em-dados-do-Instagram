"""Teto só do UGC (`--teto-ugc`, ADR 0044, issue #307).

O actor de UGC não filtra por data: o teto próprio é o único freio dele. Posts e reels seguem a regra da ADR 0043
(sem `--teto`, sem teto)."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

import pytest
from test_coleta_coletar import HOJE, LINK, _governadores

from src.coleta import cli, hf
from src.coleta.calibracao import Calibracao, calibrar
from src.coleta.coletar import _avisar_truncados, criar_scraper
from src.coleta.custo import SemEstimativa, estimar_custo
from src.coleta.manifesto import gerar_manifesto, validar_manifesto
from src.coleta.recorte import Recorte, gerar_tag, tag_valida

AGORA = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
EXTRACAO = date(2026, 10, 9)


@pytest.fixture(autouse=True)
def _governadores_falsos(monkeypatch):
    monkeypatch.setattr(cli, "_carregar_governadores", lambda: ([LINK], ["gov_a"], _governadores()))


@pytest.fixture(autouse=True)
def _sem_rede_no_hf(monkeypatch):
    def sem_hf(*_a, **_k):
        raise hf.ErroColetaHF("HF bloqueado nos testes")

    monkeypatch.setattr(hf, "ClienteColetaHFReal", sem_hf)


def _fabrica_proibida(*_a):
    raise AssertionError("scraper real nao pode ser criado sem --yes")


def _base(*, teto=None, teto_ugc=None, ugc=2) -> Calibracao:
    return Calibracao(
        n_governadores=1,
        origem="coleta_2026-10-06_ultimos-5d",
        dias_janela=5,
        base_teto=teto,
        base_teto_ugc=teto_ugc,
        n_perfis_base=1,
        contagens={"posts": {"gov_a": 5}, "reels": {"gov_a": 3}, "ugc": {"gov_a": ugc}},
    )


# --- Recorte e identificador --------------------------------------------------------------


def test_identificador_traz_o_teto_ugc_depois_do_teto_e_antes_do_rotulo():
    recorte = Recorte(inicio=date(2026, 4, 4), fim=date(2026, 10, 25), teto_ugc=3000)
    tag = gerar_tag(recorte, EXTRACAO, "tcc")
    assert tag == "coleta_2026-10-09_de-2026-04-04_ate-2026-10-25_teto-ugc-3000_tcc"
    assert tag_valida(tag)

    com_os_dois = gerar_tag(Recorte(dias=90, teto=250, teto_ugc=3000), EXTRACAO)
    assert com_os_dois == "coleta_2026-10-09_ultimos-90d_teto-250_teto-ugc-3000"
    assert tag_valida(com_os_dois)


def test_identificador_sem_teto_ugc_continua_igual_ao_de_hoje():
    assert gerar_tag(Recorte(dias=90, teto=250), EXTRACAO) == "coleta_2026-10-09_ultimos-90d_teto-250"


def test_rotulo_nao_pode_imitar_o_segmento_teto_ugc():
    with pytest.raises(ValueError, match="Rótulo"):
        gerar_tag(Recorte(dias=90), EXTRACAO, "teto-ugc-5")


def test_teto_ugc_invalido_e_so_teto_ugc_nao_bastam_como_recorte():
    with pytest.raises(ValueError, match="teto_ugc"):
        Recorte(dias=90, teto_ugc=0)
    with pytest.raises(ValueError, match="vazio"):  # sem janela, posts e reels ficariam ilimitados
        Recorte(teto_ugc=3000)


# --- scraper: o resultsLimit de cada actor ------------------------------------------------


class _ClienteFalso:
    def __init__(self):
        self.inputs: dict[str, dict] = {}

    def actor(self, actor_id):
        outer = self

        class Ator:
            def call(self, run_input=None, **_kw):
                outer.inputs[actor_id] = run_input
                return {"id": "run1", "defaultDatasetId": "ds1"}

        return Ator()

    def dataset(self, _id):
        class Dataset:
            def list_items(self):
                class Itens:
                    items: list = []

                return Itens()

        return Dataset()

    def run(self, _id):
        class Run:
            def get(self):
                return {}

        return Run()


def _limites_enviados(recorte: Recorte) -> dict[str, object]:
    cliente = _ClienteFalso()
    scraper = criar_scraper(cliente, recorte, HOJE)
    for chamar in (scraper.scrape_posts, scraper.scrape_reels, scraper.scrape_mentions):
        try:
            chamar(["gov_a"])
        except Exception:  # noqa: BLE001 - só o input enviado importa aqui
            pass
    return {
        "posts": cliente.inputs["apify/instagram-post-scraper"].get("resultsLimit", "omitido"),
        "reels": cliente.inputs["apify/instagram-reel-scraper"].get("resultsLimit", "omitido"),
        "ugc": cliente.inputs["apify/instagram-tagged-scraper"].get("resultsLimit", "omitido"),
    }


def test_so_teto_ugc_limita_o_ugc_e_posts_e_reels_omitem_o_resultslimit():
    assert _limites_enviados(Recorte(dias=90, teto_ugc=3000)) == {"posts": "omitido", "reels": "omitido", "ugc": 3000}


def test_teto_ugc_tem_precedencia_no_ugc_sobre_o_teto_geral():
    assert _limites_enviados(Recorte(dias=90, teto=250, teto_ugc=3000)) == {"posts": 250, "reels": 250, "ugc": 3000}


def test_sem_teto_ugc_o_comportamento_nao_muda():
    assert _limites_enviados(Recorte(dias=90, teto=250)) == {"posts": 250, "reels": 250, "ugc": 250}
    assert _limites_enviados(Recorte(dias=90)) == {"posts": "omitido", "reels": "omitido", "ugc": "omitido"}


# --- estimativa de custo ------------------------------------------------------------------


def test_so_teto_ugc_da_maximo_so_do_ugc_e_o_total_continua_sem_maximo():
    custo = estimar_custo(Recorte(dias=90, teto_ugc=3000), 26, HOJE, "BRONZE", _base())

    assert custo["teto"] == {"sem_teto": True, "ugc_itens_por_perfil": 3000}
    assert "maximo_usd" not in custo
    assert custo["maximo_ugc_usd"] == pytest.approx(26 * 3000 / 1000 * 2.30)


def test_teto_ugc_com_teto_geral_calcula_o_maximo_de_cada_colecao_com_o_seu_teto():
    custo = estimar_custo(Recorte(dias=90, teto=250, teto_ugc=3000), 26, HOJE, "BRONZE", _base())

    assert custo["teto"] == {"aplicado_itens_por_perfil": 250, "padrao": False, "ugc_itens_por_perfil": 3000}
    maximo = custo["maximo_usd"]
    assert maximo["ugc"] == pytest.approx(26 * 3000 / 1000 * 2.30)
    assert maximo["posts"] == pytest.approx(26 * 250 / 1000 * 2.30)


def test_teto_ugc_sem_base_estima_o_ugc_pelo_maximo_mas_posts_e_reels_seguem_sem_estimativa():
    with pytest.raises(SemEstimativa, match="posts"):
        estimar_custo(Recorte(dias=90, teto_ugc=3000), 26, HOJE, "BRONZE", None)


def test_ugc_da_base_que_bateu_o_teto_ugc_da_base_esta_censurado_e_sobe_ao_novo_teto_ugc():
    # a base limitou o UGC em 50 (o governador chegou a 50) e posts/reels sem teto: só o UGC censura
    base = _base(teto=None, teto_ugc=50, ugc=50)
    custo = estimar_custo(Recorte(dias=90, teto_ugc=3000), 1, HOJE, "BRONZE", base)

    assert custo["resultados_itens"]["ugc"] == 3000
    assert custo["resultados_itens"]["posts"] == 90  # 5 itens em 5 dias -> 90 em 90 dias, sem censura


# --- calibração: teto próprio do UGC na Coleta de origem ---------------------------------


def _coleta_base(recorte: Recorte, ugc_itens: int) -> hf.ColetaListada:
    def fonte(itens):
        return {"itens": itens, "mais_antiga": None, "mais_recente": None, "por_perfil": [{"username": "gov_a", "itens": itens}]}

    return hf.ColetaListada(
        coleta="coleta_2026-10-01_ultimos-5d_teto-ugc-50",
        commit="abc",
        recorte=recorte,
        cobertura={
            "posts": fonte(5),
            "reels": fonte(3),
            "perfis": {"itens": 1, "mais_antiga": None, "mais_recente": None, "por_perfil": []},
            "ugc": fonte(ugc_itens),
        },
        extraido_em=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
        sem_teto=recorte.teto is None,
    )


def test_calibrar_le_o_teto_ugc_da_coleta_de_origem_e_so_o_ugc_conta_como_truncado():
    c = calibrar(_coleta_base(Recorte(dias=5, teto_ugc=50), ugc_itens=50), ["gov_a"])

    assert (c.base_teto, c.base_teto_ugc) == (None, 50)
    assert c.base_teto_de("ugc") == 50 and c.base_teto_de("posts") is None
    assert c.perfis_truncados == 1


# --- manifesto ----------------------------------------------------------------------------


def _manifesto(snapshot, recorte: Recorte, calibracao: Calibracao | None = None):
    return gerar_manifesto(
        snapshot,
        tag=gerar_tag(recorte, EXTRACAO),
        recorte=recorte,
        extraido_em=AGORA,
        versao_codigo="abc123def456",
        custo_estimado=estimar_custo(recorte, 2, EXTRACAO, calibracao=calibracao or _base()),
    )


def test_manifesto_registra_o_teto_ugc_valida_e_nao_tem_campo_nulo(tmp_path):
    for recorte in (Recorte(dias=90, teto_ugc=3000), Recorte(dias=90, teto=250, teto_ugc=3000)):
        m = _manifesto(tmp_path, recorte)
        validar_manifesto(m)
        assert m["recorte"]["teto_ugc"] == 3000
        assert m["custo"]["estimado"]["teto"]["ugc_itens_por_perfil"] == 3000
        assert "null" not in json.dumps({"recorte": m["recorte"], "custo": m["custo"]})


def test_manifesto_sem_teto_ugc_nao_ganha_chave_nova(tmp_path):
    m = _manifesto(tmp_path, Recorte(dias=90, teto=250))
    assert "teto_ugc" not in m["recorte"]
    assert "ugc_itens_por_perfil" not in m["custo"]["estimado"]["teto"]
    validar_manifesto(m)


def test_maximo_ugc_sem_o_teto_correspondente_e_incoerente(tmp_path):
    m = _manifesto(tmp_path, Recorte(dias=90, teto_ugc=3000))
    sem_teto_ugc = json.loads(json.dumps(m))
    del sem_teto_ugc["custo"]["estimado"]["teto"]["ugc_itens_por_perfil"]
    with pytest.raises(ValueError, match="maximo_ugc_usd"):
        validar_manifesto(sem_teto_ugc)


# --- aviso de truncamento -----------------------------------------------------------------


def test_aviso_de_truncados_usa_o_teto_de_cada_colecao_e_mostra_a_data_mais_antiga_do_ugc(caplog):
    marcacoes = [{"inputUrl": "gov_a", "timestamp": f"2026-0{m}-15T10:00:00Z"} for m in (5, 6, 7)]
    bruto = {"posts": [{"inputUrl": "gov_a"}] * 2, "reels": [], "ugc_mentions": marcacoes}

    with caplog.at_level(logging.WARNING):
        _avisar_truncados(bruto, Recorte(dias=90, teto_ugc=3))

    texto = caplog.text
    assert "ugc_mentions" in texto and "--teto-ugc" in texto
    assert "2026-05-15" in texto  # a marcação mais antiga que o perfil alcançou
    assert "posts" not in texto.replace("ugc_mentions", "")  # posts sem teto: nada a avisar


def test_sem_nenhum_teto_nao_ha_aviso_de_truncamento(caplog):
    with caplog.at_level(logging.WARNING):
        _avisar_truncados({"posts": [{"inputUrl": "gov_a"}] * 5, "reels": [], "ugc_mentions": []}, Recorte(dias=90))
    assert caplog.text == ""


# --- CLI ----------------------------------------------------------------------------------


def _base_hf() -> hf.ColetaListada:
    def fonte(itens):
        return {"itens": itens, "mais_antiga": None, "mais_recente": None, "por_perfil": [{"username": "gov_a", "itens": itens}]}

    return hf.ColetaListada(
        coleta="coleta_2026-10-06_ultimos-5d",
        commit="abc",
        recorte=Recorte(dias=5),
        cobertura={
            "posts": fonte(5),
            "reels": fonte(3),
            "perfis": {"itens": 1, "mais_antiga": None, "mais_recente": None, "por_perfil": []},
            "ugc": fonte(2),
        },
        extraido_em=AGORA,
        sem_teto=True,
    )


def test_cli_so_teto_ugc_mostra_o_teto_do_ugc_e_o_maximo_so_dele(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(hf, "listar", lambda *, cliente: [_base_hf()])
    destino = tmp_path / "dados"

    codigo = cli.main(
        ["coletar", "--dias", "90", "--teto-ugc", "3000", "--destino", str(destino)],
        scraper_factory=_fabrica_proibida,
        cliente_factory=lambda: object(),
        agora=AGORA,
    )
    saida = capsys.readouterr().out

    assert codigo == 0
    assert "sem teto" in saida and "UGC: ate 3.000 itens por perfil" in saida
    assert "maximo so do UGC" in saida
    assert "Maximo (US$)" not in saida  # o total continua sem máximo
    assert all(linha.isascii() for linha in saida.splitlines())
    assert not destino.exists()


def test_cli_teto_e_teto_ugc_mostram_o_maximo_de_itens_de_cada_colecao(tmp_path, capsys):
    codigo = cli.main(
        ["coletar", "--dias", "90", "--teto", "250", "--teto-ugc", "3000", "--destino", str(tmp_path / "dados")],
        scraper_factory=_fabrica_proibida,
        agora=AGORA,
    )
    saida = capsys.readouterr().out

    assert codigo == 0
    assert "250 / 250" in saida  # posts e reels, 1 governador falso
    assert "3.000" in saida  # UGC com o teto próprio
    assert "Maximo (US$)" in saida


def test_cli_teto_ugc_invalido_e_erro_claro_sem_traceback(tmp_path, capsys):
    codigo = cli.main(
        ["coletar", "--dias", "90", "--teto-ugc", "0", "--destino", str(tmp_path / "dados")],
        scraper_factory=_fabrica_proibida,
        agora=AGORA,
    )
    captura = capsys.readouterr()

    assert codigo == 1
    assert "teto_ugc" in captura.err and "Traceback" not in captura.err


def test_cli_so_teto_ugc_sem_janela_e_recusado(tmp_path, capsys):
    codigo = cli.main(
        ["coletar", "--teto-ugc", "3000", "--destino", str(tmp_path / "dados")],
        scraper_factory=_fabrica_proibida,
        agora=AGORA,
    )
    captura = capsys.readouterr()

    assert codigo == 1 and "vazio" in captura.err
