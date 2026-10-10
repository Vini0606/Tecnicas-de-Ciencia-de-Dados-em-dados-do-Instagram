"""Restaurar uma Coleta antiga na main (ADR 0039, issue #250). Cliente HF falso, sem rede."""

from __future__ import annotations

import json

import pytest

from src.coleta.hf import ErroColetaHF, ErroTagExistente, Plano, publicar, restaurar
from src.coleta.recorte import tag_valida
from tests.test_coleta_hf import TAG, TAG2, ClienteFake, _segundo_snapshot, _sim, _snapshot

TAG_RESTAURADA = TAG + "_restaurada"


def _com_duas_coletas(tmp_path):
    cliente = ClienteFake()
    publicar(_snapshot(tmp_path / "s1"), cliente=cliente, confirmar=_sim)
    publicar(_segundo_snapshot(tmp_path / "s2"), cliente=cliente, confirmar=_sim)
    return cliente


def test_restaurar_gera_novo_commit_e_tag_nova_mantendo_a_original(tmp_path):
    cliente = _com_duas_coletas(tmp_path)
    commits_antes = len(cliente.commits)
    original = dict(cliente.commits[cliente.tags[TAG]])
    tags_antes = dict(cliente.tags)

    r = restaurar(TAG, cliente=cliente, confirmar=_sim)

    assert r.publicado is True
    assert r.tag == TAG_RESTAURADA
    assert tag_valida(TAG_RESTAURADA)
    assert len(cliente.commits) == commits_antes + 1  # exatamente um commit novo
    assert cliente.tags[TAG_RESTAURADA] == len(cliente.commits) - 1
    assert {k: v for k, v in cliente.tags.items() if k != TAG_RESTAURADA} == tags_antes
    assert cliente.commits[cliente.tags[TAG]] == original  # historico intacto


def test_restaurar_poe_o_conteudo_da_tag_na_main(tmp_path):
    cliente = _com_duas_coletas(tmp_path)

    restaurar(TAG, cliente=cliente, confirmar=_sim)

    main = cliente.listar_arquivos()
    assert "bronze/instagram_posts/part-1.parquet" in main
    assert "bronze/instagram_posts/part-2.parquet" not in main  # da Coleta mais nova
    manifesto = json.loads(cliente.ler_arquivo("manifesto.json").decode())
    assert manifesto["identidade"]["tag"] == TAG_RESTAURADA
    # o manifesto da tag original continua dizendo a tag original
    original = json.loads(cliente.ler_arquivo("manifesto.json", TAG).decode())
    assert original["identidade"]["tag"] == TAG


def test_restaurar_confirmacao_recebe_o_alvo_exato_e_sem_sim_nada_muda(tmp_path):
    cliente = _com_duas_coletas(tmp_path)
    commits, tags = len(cliente.commits), dict(cliente.tags)
    vistos: list[Plano] = []

    def nao(plano: Plano) -> bool:
        vistos.append(plano)
        return False

    r = restaurar(TAG, cliente=cliente, confirmar=nao)

    assert r.publicado is False
    assert vistos[0].tag == TAG_RESTAURADA
    assert TAG_RESTAURADA in vistos[0].descrever()
    assert len(cliente.commits) == commits and cliente.tags == tags


def test_restaurar_rotulo_proprio(tmp_path):
    cliente = _com_duas_coletas(tmp_path)

    r = restaurar(TAG, cliente=cliente, confirmar=_sim, rotulo="volta-de-teste")

    assert r.tag == TAG + "_volta-de-teste"


def test_restaurar_tag_inexistente_ou_invalida_nao_altera_nada(tmp_path):
    cliente = _com_duas_coletas(tmp_path)
    commits = len(cliente.commits)
    with pytest.raises(ErroColetaHF):
        restaurar("coleta_2020-01-01_teto-1", cliente=cliente, confirmar=_sim)
    with pytest.raises(ValueError):
        restaurar("qualquer", cliente=cliente, confirmar=_sim)
    assert len(cliente.commits) == commits


def test_restaurar_duas_vezes_recusa_tag_ja_existente(tmp_path):
    cliente = _com_duas_coletas(tmp_path)
    restaurar(TAG, cliente=cliente, confirmar=_sim)
    commits = len(cliente.commits)

    with pytest.raises(ErroTagExistente):
        restaurar(TAG, cliente=cliente, confirmar=_sim)

    assert len(cliente.commits) == commits


def test_restaurar_a_coleta_mais_nova_tambem_funciona(tmp_path):
    cliente = _com_duas_coletas(tmp_path)
    # a data da tag segue a extracao registrada no manifesto (fixture: 2026-10-09)
    assert restaurar(TAG2, cliente=cliente, confirmar=_sim).tag == "coleta_2026-10-09_teto-10_restaurada"
