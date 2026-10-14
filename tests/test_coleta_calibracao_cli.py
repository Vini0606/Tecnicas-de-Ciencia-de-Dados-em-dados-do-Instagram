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
    assert "1/1 governadores com taxa propria" in saida
    assert all(len(linha) < 80 for linha in saida.splitlines() if "ABORTADO" not in linha)


def test_hf_com_erro_cai_nas_taxas_fixas_e_diz_o_motivo(tmp_path, capsys):
    def quebra():
        raise hf.ErroColetaHF("sem token")

    saida = _estimar(tmp_path, capsys, cliente_factory=quebra)

    assert "taxas fixas da ADR 0012" in saida
    assert "HF indisponivel" in saida
    assert "Esperado (US$)" in saida  # a estimativa sai mesmo assim


def test_coleta_anterior_curta_cai_nas_taxas_fixas_com_o_motivo(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(hf, "listar", lambda *, cliente: [_coleta([_perfil("gov_a", 30)], dias=5, teto=30)])

    saida = _estimar(tmp_path, capsys, cliente_factory=lambda: object())

    assert "taxas fixas da ADR 0012" in saida and "curta demais" in saida


def test_sem_calibracao_nunca_consulta_o_hf(tmp_path, capsys):
    def nao_deve_ser_chamado():
        raise AssertionError("--sem-calibracao nao pode tocar no HF")

    saida = _estimar(tmp_path, capsys, "--sem-calibracao", cliente_factory=nao_deve_ser_chamado)

    assert "taxas fixas da ADR 0012" in saida and "--sem-calibracao" in saida


def test_calibracao_muda_o_esperado_e_nao_o_pior_caso(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(hf, "listar", lambda *, cliente: [_coleta([_perfil("gov_a", 90)], [_perfil("gov_a", 45)])])

    calibrada = _estimar(tmp_path / "a", capsys, cliente_factory=lambda: object())
    fixa = _estimar(tmp_path / "b", capsys, "--sem-calibracao", cliente_factory=lambda: object())

    def total(saida):  # colunas do Total: esperado, pior caso
        return next(linha.split()[1:] for linha in saida.splitlines() if linha.split()[:1] == ["Total"])

    esperado_calibrado, pior_calibrado = total(calibrada)
    esperado_fixo, pior_fixo = total(fixa)
    assert pior_calibrado == pior_fixo
    assert float(esperado_calibrado.replace(",", ".")) < float(esperado_fixo.replace(",", "."))
