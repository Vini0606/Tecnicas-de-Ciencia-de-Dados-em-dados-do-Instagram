"""Landing em toda Coleta (ADR 0045, issue #310): o payload bruto da Apify, sem filtro do Recorte.

Seams: `coletar` com scraper falso, o módulo `hf` com o cliente falso e o manifesto. Nenhuma rede, nenhum gasto."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from test_coleta_coletar import HOJE, _coletar, _post, _reel, _ScraperFalso

from src.coleta.recorte import Recorte

AGORA = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
FONTES = ("profiles", "posts", "reels", "ugc_mentions")


def _ler(destino: Path, run_id: str, fonte: str):
    return json.loads((destino / "landing" / run_id / f"{fonte}.json").read_text(encoding="utf-8"))


def _scraper_com_itens_fora_da_janela():
    return _ScraperFalso(
        posts=[
            _post("dentro", "2026-08-20T10:00:00.000Z"),
            _post("depois-do-fim", "2026-09-05T10:00:00.000Z"),  # o actor devolve, o Recorte descarta
        ],
        reels=[_reel("r1", "2026-08-12T10:00:00.000Z")],
        mentions=[
            {"id": "u1", "ownerUsername": "fulano", "inputUrl": "https://www.instagram.com/gov_a/", "timestamp": "2026-08-15T10:00:00.000Z"},
            {"url": "https://www.instagram.com/gov_a/", "error": "no_items", "errorDescription": "Empty or private data"},
        ],
    )


RECORTE_ABSOLUTO = Recorte(inicio=date(2026, 8, 1), fim=date(2026, 8, 31), teto=100)


# --- coletar: a landing é o payload sem filtro ---------------------------------------------


def test_coletar_grava_a_landing_com_os_itens_fora_do_recorte_e_os_registros_de_erro(tmp_path):
    resultado = _coletar(tmp_path, RECORTE_ABSOLUTO, _scraper_com_itens_fora_da_janela())

    destino = tmp_path / "dados"
    posts = _ler(destino, resultado.run_id, "posts")
    assert [p["id"] for p in posts] == ["dentro", "depois-do-fim"]  # sem o filtro do Recorte
    assert [r["id"] for r in _ler(destino, resultado.run_id, "reels")] == ["r1"]
    ugc = _ler(destino, resultado.run_id, "ugc_mentions")
    assert len(ugc) == 2 and ugc[1]["error"] == "no_items"  # o erro da Apify também é payload
    assert _ler(destino, resultado.run_id, "profiles")[0]["username"] == "gov_a"


def test_a_bronze_continua_filtrada_pelo_recorte_enquanto_a_landing_nao(tmp_path):
    from deltalake import DeltaTable

    resultado = _coletar(tmp_path, RECORTE_ABSOLUTO, _scraper_com_itens_fora_da_janela())

    destino = tmp_path / "dados"
    bronze = DeltaTable(str(destino / "bronze" / "instagram_posts")).to_pandas()
    assert list(bronze["id"]) == ["dentro"]
    assert len(_ler(destino, resultado.run_id, "posts")) == 2


def test_so_estimar_nao_escreve_nem_a_landing(tmp_path):
    from src.coleta.coletar import ColetaNaoConfirmada

    with pytest.raises(ColetaNaoConfirmada):
        _coletar(tmp_path, RECORTE_ABSOLUTO, _ScraperFalso(), confirmar=lambda custo: False)

    assert not (tmp_path / "dados").exists()


def test_falha_do_ugc_nao_apaga_a_landing_ja_gravada(tmp_path):
    class UgcQuebra(_ScraperFalso):
        def scrape_mentions(self, links, extra_run_input=None):
            raise RuntimeError("apify caiu")

    resultado = _coletar(tmp_path, RECORTE_ABSOLUTO, UgcQuebra())

    destino = tmp_path / "dados"
    assert [p["id"] for p in _ler(destino, resultado.run_id, "posts")] == ["p1"]
    assert not (destino / "landing" / resultado.run_id / "ugc_mentions.json").exists()


# --- manifesto v6 ----------------------------------------------------------------------------


def test_manifesto_registra_a_landing_com_itens_e_bytes_por_fonte_e_valida(tmp_path):
    from src.coleta.manifesto import validar_manifesto

    resultado = _coletar(tmp_path, RECORTE_ABSOLUTO, _scraper_com_itens_fora_da_janela())

    m = resultado.manifesto
    validar_manifesto(m)
    assert m["versao_esquema"] == 6
    assert m["landing"]["run_id"] == resultado.run_id
    fontes = m["landing"]["fontes"]
    assert {k: v["itens"] for k, v in fontes.items()} == {"perfis": 1, "posts": 2, "reels": 1, "ugc": 2}
    arquivo = tmp_path / "dados" / "landing" / resultado.run_id / "posts.json"
    assert fontes["posts"]["bytes"] == arquivo.stat().st_size
    assert "null" not in json.dumps(m["landing"])


def test_a_landing_so_vale_no_esquema_v6_e_nao_aceita_campo_extra(tmp_path):
    from src.coleta.manifesto import validar_manifesto

    m = _coletar(tmp_path, RECORTE_ABSOLUTO, _ScraperFalso()).manifesto

    antigo = json.loads(json.dumps(m))
    antigo["versao_esquema"] = 5
    with pytest.raises(ValueError, match="manifesto"):
        validar_manifesto(antigo)

    com_extra = json.loads(json.dumps(m))
    com_extra["landing"]["fontes"]["posts"]["texto"] = "x"
    with pytest.raises(ValueError, match="landing"):
        validar_manifesto(com_extra)


def test_snapshot_sem_landing_gera_manifesto_v6_sem_o_bloco(tmp_path):
    import shutil

    from src.coleta.manifesto import gerar_manifesto, validar_manifesto

    resultado = _coletar(tmp_path, RECORTE_ABSOLUTO, _ScraperFalso())
    destino = tmp_path / "dados"
    shutil.rmtree(destino / "landing")

    m = gerar_manifesto(
        destino, tag=resultado.tag, recorte=RECORTE_ABSOLUTO, extraido_em=AGORA, versao_codigo="abc123def456"
    )
    validar_manifesto(m)
    assert m["versao_esquema"] == 6 and "landing" not in m


# --- HF: publicar, baixar e restaurar levam a landing ----------------------------------------------

RUN = "20261008_120000_abcd1234"
ARQ_LANDING = {f"landing/{RUN}/{f}.json": b"[]" * 10 for f in ("profiles", "posts", "reels", "ugc_mentions")}


def _manifesto_v6(tag, com_landing: bool) -> dict:
    from test_coleta_hf import _manifesto

    m = _manifesto(tag, 90, 250)
    m.update(versao_esquema=6, recorte={"dias": 90, "teto": 250}, custo={})
    if com_landing:
        m["landing"] = {
            "run_id": RUN,
            "fontes": {f: {"itens": 0, "bytes": 20} for f in ("perfis", "posts", "reels", "ugc")},
        }
    return m


def _snapshot_v6(base: Path, tag: str, com_landing: bool = True):
    from test_coleta_hf import _snapshot

    arquivos = {
        "bronze/instagram_posts/part-1.parquet": b"x" * 100,
        "silver/posts/part-1.parquet": b"y" * 50,
        "gold/governor_engagement/part-1.parquet": b"z" * 50,
        **(ARQ_LANDING if com_landing else {}),
    }
    return _snapshot(base, arquivos, _manifesto_v6(tag, com_landing))


def test_publicar_envia_a_landing_e_conta_os_bytes_dela_no_plano(tmp_path):
    from test_coleta_hf import TAG, ClienteFake, _sim
    from src.coleta.hf import publicar

    cliente = ClienteFake()
    snap = _snapshot_v6(tmp_path / "a", TAG)
    resultado = publicar(snap, cliente=cliente, confirmar=_sim)

    assert set(ARQ_LANDING) <= set(cliente.listar_arquivos())
    assert set(ARQ_LANDING) <= set(resultado.plano.adicionar)
    total_da_pasta = sum(p.stat().st_size for p in snap.rglob("*") if p.is_file())
    assert resultado.plano.bytes_envio == total_da_pasta
    assert total_da_pasta > sum(len(v) for v in ARQ_LANDING.values())  # a landing está no total


def test_o_limite_de_bytes_considera_a_landing(tmp_path):
    from test_coleta_hf import TAG, ClienteFake
    from src.coleta.hf import ErroLimiteArmazenamento, planejar

    with pytest.raises(ErroLimiteArmazenamento):
        planejar(_snapshot_v6(tmp_path / "a", TAG), cliente=ClienteFake(), limite_bytes=250)


def test_publicar_uma_coleta_sem_landing_apaga_a_landing_da_anterior_da_main(tmp_path):
    from test_coleta_hf import TAG, TAG2, ClienteFake, _sim
    from src.coleta.hf import publicar

    cliente = ClienteFake()
    publicar(_snapshot_v6(tmp_path / "a", TAG), cliente=cliente, confirmar=_sim)

    resultado = publicar(_snapshot_v6(tmp_path / "b", TAG2, com_landing=False), cliente=cliente, confirmar=_sim)

    assert set(ARQ_LANDING) <= set(resultado.plano.apagar)
    assert not any(c.startswith("landing/") for c in cliente.listar_arquivos())
    assert set(ARQ_LANDING) <= set(cliente.listar_arquivos("1"))  # a Coleta anterior segue no commit dela


def test_planejar_recusa_landing_sem_registro_no_manifesto_e_registro_sem_landing(tmp_path):
    from test_coleta_hf import TAG, ClienteFake, _snapshot
    from src.coleta.hf import ErroColetaHF, planejar

    sem_registro = _snapshot(
        tmp_path / "a", {"bronze/x/p.parquet": b"1", **ARQ_LANDING}, _manifesto_v6(TAG, com_landing=False)
    )
    with pytest.raises(ErroColetaHF, match="landing"):
        planejar(sem_registro, cliente=ClienteFake())

    sem_arquivos = _snapshot(tmp_path / "b", {"bronze/x/p.parquet": b"1"}, _manifesto_v6(TAG, com_landing=True))
    with pytest.raises(ErroColetaHF, match="landing"):
        planejar(sem_arquivos, cliente=ClienteFake())


def test_baixar_traz_a_landing_por_padrao_e_pode_pula_la_e_coleta_antiga_baixa_normal(tmp_path):
    from test_coleta_hf import TAG, TAG2, ClienteFake, _sim
    from src.coleta.hf import baixar, publicar

    cliente = ClienteFake()
    publicar(_snapshot_v6(tmp_path / "a", TAG), cliente=cliente, confirmar=_sim)

    completo = baixar(TAG, tmp_path / "completo", cliente=cliente)
    sem = baixar(TAG, tmp_path / "sem", cliente=cliente, com_landing=False)
    assert (completo / "landing" / RUN / "posts.json").is_file()
    assert not (sem / "landing").exists() and (sem / "silver" / "posts" / "part-1.parquet").is_file()

    publicar(_snapshot_v6(tmp_path / "b", TAG2, com_landing=False), cliente=cliente, confirmar=_sim)
    antiga = baixar(TAG2, tmp_path / "antiga", cliente=cliente)
    assert not (antiga / "landing").exists()


def test_restaurar_preserva_a_landing_da_coleta_restaurada(tmp_path):
    from test_coleta_hf import TAG, TAG2, ClienteFake, _sim
    from src.coleta.hf import publicar, restaurar

    cliente = ClienteFake()
    publicar(_snapshot_v6(tmp_path / "a", TAG), cliente=cliente, confirmar=_sim)
    publicar(_snapshot_v6(tmp_path / "b", TAG2, com_landing=False), cliente=cliente, confirmar=_sim)
    assert not any(c.startswith("landing/") for c in cliente.listar_arquivos())

    restaurar(TAG, cliente=cliente, confirmar=_sim)

    assert set(ARQ_LANDING) <= set(cliente.listar_arquivos())


def test_restaurar_coleta_antiga_com_landing_e_manifesto_sem_o_bloco_funciona(tmp_path):
    """O Reboot tem landing/ na pasta e manifesto v<6 sem o bloco: restaurar não pode ser bloqueado."""
    from test_coleta_hf import TAG, TAG2, ClienteFake, _sim, _snapshot
    from src.coleta.hf import publicar, restaurar

    antigo = _manifesto_v6(TAG, com_landing=False)
    antigo["versao_esquema"] = 5
    cliente = ClienteFake()
    publicar(_snapshot(tmp_path / "a", {"bronze/x/p.parquet": b"1", **ARQ_LANDING}, antigo), cliente=cliente, confirmar=_sim)
    publicar(_snapshot_v6(tmp_path / "b", TAG2, com_landing=False), cliente=cliente, confirmar=_sim)

    restaurar(TAG, cliente=cliente, confirmar=_sim)

    assert set(ARQ_LANDING) <= set(cliente.listar_arquivos())


# --- CLI: registrar a landing de uma Coleta já extraída -----------------------------------------------


def _como_a_coleta_do_tcc(tmp_path):
    """Uma Coleta extraída antes da landing: manifesto v5 sem o bloco, com a landing já posta na pasta."""
    resultado = _coletar(tmp_path, RECORTE_ABSOLUTO, _scraper_com_itens_fora_da_janela())
    destino = tmp_path / "dados"
    m = json.loads((destino / "manifesto.json").read_text(encoding="utf-8"))
    m["versao_esquema"] = 5
    del m["landing"]
    (destino / "manifesto.json").write_text(json.dumps(m), encoding="utf-8")
    return destino, resultado.run_id


def test_cli_landing_registra_no_manifesto_a_landing_ja_presente_e_sobe_para_v6(tmp_path, capsys):
    from src.coleta import cli
    from src.coleta.manifesto import validar_manifesto

    destino, run_id = _como_a_coleta_do_tcc(tmp_path)

    codigo = cli.main(["landing", str(destino)])

    m = json.loads((destino / "manifesto.json").read_text(encoding="utf-8"))
    validar_manifesto(m)
    assert codigo == 0 and m["versao_esquema"] == 6
    assert m["landing"]["run_id"] == run_id
    assert {k: v["itens"] for k, v in m["landing"]["fontes"].items()} == {"perfis": 1, "posts": 2, "reels": 1, "ugc": 2}
    assert "posts" in capsys.readouterr().out
    assert cli.main(["landing", str(destino)]) == 0  # idempotente


def test_cli_landing_recusa_pasta_incompleta_ou_json_invalido_sem_alterar_o_manifesto(tmp_path, capsys):
    from src.coleta import cli

    destino, run_id = _como_a_coleta_do_tcc(tmp_path)
    antes = (destino / "manifesto.json").read_text(encoding="utf-8")

    (destino / "landing" / run_id / "reels.json").unlink()
    assert cli.main(["landing", str(destino)]) == 1
    assert "reels" in capsys.readouterr().err

    (destino / "landing" / run_id / "reels.json").write_text("{nao e lista", encoding="utf-8")
    assert cli.main(["landing", str(destino)]) == 1

    (destino / "landing" / run_id / "reels.json").write_text('{"a": 1}', encoding="utf-8")
    assert cli.main(["landing", str(destino)]) == 1  # objeto, nao lista
    assert (destino / "manifesto.json").read_text(encoding="utf-8") == antes


def test_cli_landing_sem_pasta_de_landing_e_erro_claro(tmp_path, capsys):
    import shutil

    from src.coleta import cli

    destino, _ = _como_a_coleta_do_tcc(tmp_path)
    shutil.rmtree(destino / "landing")

    assert cli.main(["landing", str(destino)]) == 1
    assert "landing" in capsys.readouterr().err
