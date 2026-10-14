"""CLI da Coleta (issue #252): nenhuma rede, nenhum gasto, nenhum segredo."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from test_coleta_coletar import LINK, _governadores, _ScraperFalso
from test_coleta_hf import TAG, ClienteFake, _snapshot

from src.coleta import cli

AGORA = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _governadores_falsos(monkeypatch):
    monkeypatch.setattr(cli, "_carregar_governadores", lambda: ([LINK], ["gov_a"], _governadores()))


def _fabrica_proibida(*_a):
    raise AssertionError("scraper real nao pode ser criado sem --yes")


def test_coletar_sem_yes_mostra_custo_e_nao_gasta_nem_escreve(tmp_path, capsys):
    destino = tmp_path / "dados"
    codigo = cli.main(
        ["coletar", "--dias", "90", "--teto", "250", "--destino", str(destino)],
        scraper_factory=_fabrica_proibida,
        agora=AGORA,
    )
    saida = capsys.readouterr().out
    assert codigo == 0
    assert "Custo estimado" in saida and "total ~US$" in saida
    assert "ABORTADO" in saida
    assert "Janela: 2026-07-11 a 2026-10-09 (aproximada)" in saida
    assert not destino.exists()


def test_estimativa_janela_absoluta_e_so_teto(tmp_path, capsys):
    cli.main(
        ["coletar", "--inicio", "2026-03-01", "--fim", "2026-06-30", "--destino", str(tmp_path / "a")],
        scraper_factory=_fabrica_proibida,
        agora=AGORA,
    )
    saida = capsys.readouterr().out
    assert "Janela: 2026-03-01 a 2026-06-30\n" in saida
    assert "aproximada" not in saida

    cli.main(
        ["coletar", "--teto", "10", "--destino", str(tmp_path / "b")],
        scraper_factory=_fabrica_proibida,
        agora=AGORA,
    )
    assert "Janela:" not in capsys.readouterr().out


def test_coletar_com_yes_grava_snapshot_com_manifesto(tmp_path, capsys):
    destino = tmp_path / "dados"
    codigo = cli.main(
        ["coletar", "--dias", "90", "--teto", "250", "--rotulo", "teste", "--destino", str(destino), "--yes"],
        scraper_factory=lambda recorte, hoje: _ScraperFalso(),
        agora=AGORA,
    )
    assert codigo == 0
    assert (destino / "manifesto.json").is_file()
    assert "coleta_2026-10-09_ultimos-90d_teto-250_teste" in capsys.readouterr().out


def test_coletar_recusa_pasta_nao_vazia(tmp_path, capsys):
    (tmp_path / "x.txt").write_text("a")
    codigo = cli.main(
        ["coletar", "--dias", "7", "--destino", str(tmp_path), "--yes"],
        scraper_factory=_fabrica_proibida,
        agora=AGORA,
    )
    assert codigo == 2 and "nao esta vazia" in capsys.readouterr().err


def test_coletar_recorte_invalido_e_erro_claro(tmp_path, capsys):
    codigo = cli.main(
        ["coletar", "--dias", "7", "--inicio", "2026-01-01", "--fim", "2026-02-01", "--destino", str(tmp_path / "d")],
        agora=AGORA,
    )
    assert codigo == 1 and "Recorte" in capsys.readouterr().err


def test_modelar_exige_destino_igual_ao_data_dir(tmp_path, capsys):
    codigo = cli.main(
        ["coletar", "--dias", "7", "--destino", str(tmp_path / "d"), "--modelar", "--yes"],
        scraper_factory=_fabrica_proibida,
        agora=AGORA,
    )
    assert codigo == 2 and "DATA_DIR" in capsys.readouterr().err


def test_publicar_sem_yes_so_mostra_o_plano(tmp_path, capsys):
    cliente = ClienteFake()
    snap = _snapshot(tmp_path / "snap")
    codigo = cli.main(["publicar", str(snap)], cliente_factory=lambda: cliente)
    saida = capsys.readouterr().out
    assert codigo == 0 and TAG in saida and "nada foi enviado" in saida
    assert cliente.tags == {}


def test_publicar_com_yes_cria_commit_sem_tag(tmp_path):
    cliente = ClienteFake()
    snap = _snapshot(tmp_path / "snap")
    assert cli.main(["publicar", str(snap), "--yes"], cliente_factory=lambda: cliente) == 0
    assert cliente.mensagens == [f"push: {TAG}"]
    assert cliente.tags == {}


def test_listar_baixar_e_restaurar(tmp_path, capsys):
    cliente = ClienteFake()
    cli.main(["publicar", str(_snapshot(tmp_path / "snap")), "--yes"], cliente_factory=lambda: cliente)
    capsys.readouterr()

    cliente.tags["reboot-iesb"] = 1
    assert cli.main(["listar"], cliente_factory=lambda: cliente) == 0
    saida = capsys.readouterr().out
    assert TAG in saida and "reboot-iesb" in saida

    pasta = tmp_path / "baixada"
    assert cli.main(["baixar", TAG, "--destino", str(pasta)], cliente_factory=lambda: cliente) == 0
    assert (pasta / "manifesto.json").is_file()

    assert cli.main(["restaurar", TAG], cliente_factory=lambda: cliente) == 0
    assert f"push: {TAG}_restaurada" not in cliente.mensagens and len(cliente.mensagens) == 1
    assert cli.main(["restaurar", TAG, "--yes"], cliente_factory=lambda: cliente) == 0
    assert cliente.mensagens[-1] == f"restore: {TAG}_restaurada"


def test_baixar_tag_inexistente_e_erro_sem_traceback(tmp_path, capsys):
    codigo = cli.main(
        ["baixar", "coleta_2026-01-01", "--destino", str(tmp_path / "x")],
        cliente_factory=lambda: ClienteFake(),
    )
    assert codigo == 1 and "[ERRO]" in capsys.readouterr().err
