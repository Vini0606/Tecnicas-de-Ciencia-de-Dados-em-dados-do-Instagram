"""CLI: a estimativa mostra de onde veio a taxa e a flag que desliga a calibração (issue #299)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from test_coleta_calibracao import _coleta, _perfil
from test_coleta_coletar import LINK, _governadores

from src.coleta import cli, hf

AGORA = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
ARGS = ["coletar", "--dias", "90", "--teto", "250"]


@pytest.fixture(autouse=True)
def _governadores_falsos(monkeypatch):
    monkeypatch.setattr(cli, "_carregar_governadores", lambda: ([LINK], ["gov_a"], _governadores()))


def _fabrica_proibida(*_a):
    raise AssertionError("scraper real nao pode ser criado sem --yes")


def _estimar(tmp_path, capsys, *extra, cliente_factory):
    cli.main(
        [*ARGS, "--destino", str(tmp_path / "dados"), *extra],
        scraper_factory=_fabrica_proibida,
        cliente_factory=cliente_factory,
        agora=AGORA,
    )
    return capsys.readouterr().out


def test_estimativa_mostra_a_coleta_de_origem_da_calibracao(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(hf, "listar", lambda *, cliente: [_coleta([_perfil("gov_a", 180)])])

    saida = _estimar(tmp_path, capsys, cliente_factory=lambda: object())

    assert "Calibracao" in saida
    assert "coleta_2026-10-01_ultimos-90d_teto-250" in saida
    assert "1/1 governadores com itens na base" in saida
    assert all(len(linha) < 120 for linha in saida.splitlines() if "ABORTADO" not in linha)


def test_hf_com_erro_vira_sem_base_estimado_igual_ao_maximo_e_diz_o_motivo(tmp_path, capsys):
    def quebra():
        raise hf.ErroColetaHF("sem token")

    saida = _estimar(tmp_path, capsys, cliente_factory=quebra)

    assert "sem base de calibracao" in saida
    assert "HF indisponivel" in saida
    assert "Estimado (US$)" in saida  # a estimativa sai mesmo assim
    assert "Sem base de calibracao: o estimado vale o maximo" in saida


def test_coleta_anterior_curta_serve_de_base_sem_aviso_de_janela_curta(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(hf, "listar", lambda *, cliente: [_coleta([_perfil("gov_a", 30)], dias=5, teto=30)])

    saida = _estimar(tmp_path, capsys, cliente_factory=lambda: object())

    assert "coleta_2026-10-01_ultimos-5d_teto-30" in saida
    assert "5 dias; 1/1 governadores com itens na base" in saida
    assert "curta demais" not in saida and "sem base de calibracao" not in saida


def test_sem_calibracao_nunca_consulta_o_hf(tmp_path, capsys):
    def nao_deve_ser_chamado():
        raise AssertionError("--sem-calibracao nao pode tocar no HF")

    saida = _estimar(tmp_path, capsys, "--sem-calibracao", cliente_factory=nao_deve_ser_chamado)

    assert "sem base de calibracao" in saida and "--sem-calibracao" in saida


def test_base_muda_o_estimado_e_nao_o_maximo(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(hf, "listar", lambda *, cliente: [_coleta([_perfil("gov_a", 90)], [_perfil("gov_a", 45)])])

    calibrada = _estimar(tmp_path / "a", capsys, cliente_factory=lambda: object())
    sem_base = _estimar(tmp_path / "b", capsys, "--sem-calibracao", cliente_factory=lambda: object())

    def total(saida):  # colunas do Total: estimado, maximo
        return next(linha.split()[1:] for linha in saida.splitlines() if linha.split()[:1] == ["Total"])

    estimado_calibrado, maximo_calibrado = total(calibrada)
    estimado_sem_base, maximo_sem_base = total(sem_base)
    assert maximo_calibrado == maximo_sem_base
    assert estimado_sem_base == maximo_sem_base  # sem base: estimado = maximo
    assert float(estimado_calibrado.replace(",", ".")) < float(estimado_sem_base.replace(",", "."))
