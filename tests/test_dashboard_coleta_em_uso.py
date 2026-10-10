"""Testes da indicacao da Coleta em uso no dashboard (ADR 0039, issue #251)."""

from __future__ import annotations

from datetime import date, datetime

from dashboard.core.coleta_em_uso import descrever_coleta, rotulo_revisao
from src.coleta.manifesto import gerar_manifesto
from src.coleta.recorte import Recorte, gerar_tag


def _manifesto(tmp_path, recorte, cobertura=None):
    tag = gerar_tag(recorte, date(2026, 10, 1))
    m = gerar_manifesto(
        tmp_path,
        tag=tag,
        recorte=recorte,
        extraido_em=datetime(2026, 10, 1, 12, 0),
        versao_codigo="abc123",
    )
    if cobertura:
        m["cobertura"]["posts"].update(cobertura)
    return m


def test_descreve_tag_recorte_e_cobertura(tmp_path):
    m = _manifesto(
        tmp_path,
        Recorte(dias=30, teto=50),
        {"itens": 10, "mais_antiga": "2026-09-02", "mais_recente": "2026-10-01"},
    )
    texto = descrever_coleta(m)
    assert m["identidade"]["tag"] in texto
    assert "ultimos 30 dias" in texto
    assert "teto 50" in texto
    assert "02/09/2026" in texto and "01/10/2026" in texto


def test_descreve_intervalo_absoluto(tmp_path):
    m = _manifesto(tmp_path, Recorte(inicio=date(2026, 8, 1), fim=date(2026, 8, 31)))
    texto = descrever_coleta(m)
    assert "01/08/2026" in texto and "31/08/2026" in texto
    assert "teto" not in texto


def test_sem_cobertura_nao_inventa_datas(tmp_path):
    texto = descrever_coleta(_manifesto(tmp_path, Recorte(teto=20)))
    assert "cobertura" in texto and "sem dados" in texto


def test_sem_manifesto_mostra_so_a_revisao():
    assert descrever_coleta(None) is None
    assert rotulo_revisao(None) == "main (Coleta vigente)"
    assert rotulo_revisao("coleta_x") == "coleta_x"
