"""Restaurar uma Coleta antiga na main (ADR 0039, issue #250). Cliente HF falso, sem rede."""

from __future__ import annotations

import json

import pytest

from src.coleta.hf import ErroColetaExistente, ErroColetaHF, Plano, publicar, restaurar
from src.coleta.recorte import tag_valida
from tests.test_coleta_hf import TAG, TAG2, ClienteFake, _segundo_snapshot, _sim, _snapshot

TAG_RESTAURADA = TAG + "_restaurada"


def _com_duas_coletas(tmp_path):
    cliente = ClienteFake()
    publicar(_snapshot(tmp_path / "s1"), cliente=cliente, confirmar=_sim)
    publicar(_segundo_snapshot(tmp_path / "s2"), cliente=cliente, confirmar=_sim)
    return cliente


def test_restaurar_gera_novo_commit_sem_tag_mantendo_o_original(tmp_path):
    cliente = _com_duas_coletas(tmp_path)
    commits_antes = len(cliente.commits)
    original = dict(cliente.commits[1])  # commit da Coleta TAG
    tags_antes = dict(cliente.tags)

    r = restaurar(TAG, cliente=cliente, confirmar=_sim)

    assert r.publicado is True
    assert r.coleta == TAG_RESTAURADA
    assert tag_valida(TAG_RESTAURADA)
    assert len(cliente.commits) == commits_antes + 1  # exatamente um commit novo
    assert cliente.mensagens[-1] == f"restore: {TAG_RESTAURADA}"
    assert cliente.tags == tags_antes  # nenhuma tag criada, movida ou apagada
    assert cliente.commits[1] == original  # historico intacto
    assert cliente.mensagens[-1] == f"restore: {TAG_RESTAURADA}"


def test_restaurar_poe_o_conteudo_da_coleta_na_main(tmp_path):
    cliente = _com_duas_coletas(tmp_path)

    restaurar(TAG, cliente=cliente, confirmar=_sim)

    main = cliente.listar_arquivos()
    assert "bronze/instagram_posts/part-1.parquet" in main
    assert "bronze/instagram_posts/part-2.parquet" not in main  # da Coleta mais nova
    manifesto = json.loads(cliente.ler_arquivo("manifesto.json").decode())
    assert manifesto["identidade"]["tag"] == TAG_RESTAURADA
    # o manifesto da tag original continua dizendo a tag original
    original = json.loads(cliente.ler_arquivo("manifesto.json", "1").decode())
    assert original["identidade"]["tag"] == TAG


def test_restaurar_por_hash_de_commit_e_por_tag_de_uso(tmp_path):
    cliente = _com_duas_coletas(tmp_path)
    cliente.tags["reboot-iesb"] = 1

    por_hash = restaurar("1", cliente=cliente, confirmar=_sim, rotulo="por-hash")
    por_tag = restaurar("reboot-iesb", cliente=cliente, confirmar=_sim, rotulo="por-tag")

    assert por_hash.coleta == TAG + "_por-hash"
    assert por_tag.coleta == TAG + "_por-tag"


def test_restaurar_confirmacao_recebe_o_alvo_exato_e_sem_sim_nada_muda(tmp_path):
    cliente = _com_duas_coletas(tmp_path)
    commits, tags = len(cliente.commits), dict(cliente.tags)
    vistos: list[Plano] = []

    def nao(plano: Plano) -> bool:
        vistos.append(plano)
        return False

    r = restaurar(TAG, cliente=cliente, confirmar=nao)

    assert r.publicado is False
    assert vistos[0].coleta == TAG_RESTAURADA
    assert TAG_RESTAURADA in vistos[0].descrever()
    assert len(cliente.commits) == commits and cliente.tags == tags


def test_restaurar_rotulo_proprio(tmp_path):
    cliente = _com_duas_coletas(tmp_path)

    r = restaurar(TAG, cliente=cliente, confirmar=_sim, rotulo="volta-de-teste")

    assert r.coleta == TAG + "_volta-de-teste"


def test_restaurar_referencia_inexistente_nao_altera_nada(tmp_path):
    cliente = _com_duas_coletas(tmp_path)
    commits = len(cliente.commits)
    with pytest.raises(ErroColetaHF):
        restaurar("coleta_2020-01-01_teto-1", cliente=cliente, confirmar=_sim)
    with pytest.raises(ErroColetaHF):
        restaurar("qualquer", cliente=cliente, confirmar=_sim)
    assert len(cliente.commits) == commits


def test_restaurar_duas_vezes_recusa_coleta_ja_publicada(tmp_path):
    cliente = _com_duas_coletas(tmp_path)
    restaurar(TAG, cliente=cliente, confirmar=_sim)
    commits = len(cliente.commits)

    with pytest.raises(ErroColetaExistente):
        restaurar(TAG, cliente=cliente, confirmar=_sim)

    assert len(cliente.commits) == commits


def test_restaurar_a_coleta_mais_nova_tambem_funciona(tmp_path):
    cliente = _com_duas_coletas(tmp_path)
    # a data da tag segue a extracao registrada no manifesto (fixture: 2026-10-09)
    assert restaurar(TAG2, cliente=cliente, confirmar=_sim).coleta == "coleta_2026-10-09_teto-10_restaurada"
