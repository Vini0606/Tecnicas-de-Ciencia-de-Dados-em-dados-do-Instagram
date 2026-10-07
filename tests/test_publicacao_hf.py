"""Testes da publicação/download das tabelas do dashboard no HF (ADR 0036).

Nunca usam a rede: o cliente HF é um fake injetado.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from src.dados_hf import ErroHF
from src.publicacao_hf import (
    PADROES_PUBLICACAO,
    ConfigHF,
    baixar,
    configuracao_hf,
    dados_presentes,
    descrever_publicacao,
    garantir_dados,
    publicar,
    tabelas_publicaveis,
)

CONFIG = ConfigHF(token="hf_segredo_123", repo="usuario/dados-dashboard")


def _tabela(base: Path, camada: str, nome: str) -> None:
    (base / camada / nome / "_delta_log").mkdir(parents=True)


class ClienteFake:
    def __init__(
        self, cria_gold_ao_baixar: bool = True, falha: Exception | None = None
    ):
        self.enviados: list[tuple[Path, list[str], str]] = []
        self.baixados: list[tuple[Path, list[str]]] = []
        self._cria = cria_gold_ao_baixar
        self._falha = falha

    def listar_arquivos(self, revisao=None):
        return []

    def enviar(self, pasta, padroes, mensagem):
        self.enviados.append((pasta, padroes, mensagem))

    def baixar(self, pasta, padroes, revisao=None):
        if self._falha:
            raise self._falha
        self.baixados.append((pasta, padroes))
        if self._cria:
            _tabela(Path(pasta), "gold", "governor_engagement")


# --------------------------------------------------------------- configuração


def test_configuracao_usa_a_primeira_fonte_completa():
    env = {"HF_TOKEN": "t"}  # sem repositório: incompleta
    secrets = {"HF_TOKEN": "t2", "HF_DATASET_REPO_PUBLICACAO": "u/d"}
    assert configuracao_hf(env, secrets) == ConfigHF(token="t2", repo="u/d")


def test_configuracao_none_sem_token_ou_sem_repositorio():
    assert configuracao_hf({}, None) is None
    assert configuracao_hf({"HF_TOKEN": "t"}) is None
    assert configuracao_hf({"HF_DATASET_REPO_PUBLICACAO": "u/d"}) is None
    assert (
        configuracao_hf({"HF_TOKEN": "  ", "HF_DATASET_REPO_PUBLICACAO": "u/d"}) is None
    )


# --------------------------------------------------------------------- tabelas


def test_tabelas_publicaveis_lista_so_delta_de_silver_e_gold(tmp_path):
    _tabela(tmp_path, "gold", "governor_nsm")
    _tabela(tmp_path, "silver", "posts_clean")
    (tmp_path / "gold" / "pasta_sem_delta").mkdir()
    _tabela(tmp_path, "bronze", "posts_raw")  # bronze nunca entra
    assert tabelas_publicaveis(tmp_path) == ["silver/posts_clean", "gold/governor_nsm"]


def test_tabelas_publicaveis_vazio_sem_diretorios(tmp_path):
    assert tabelas_publicaveis(tmp_path) == []
    assert "nada a enviar" in descrever_publicacao([])


def test_dados_presentes_depende_do_gold_de_engajamento(tmp_path):
    assert dados_presentes(tmp_path) is False
    _tabela(tmp_path, "gold", "governor_nsm")
    assert dados_presentes(tmp_path) is False
    _tabela(tmp_path, "gold", "governor_engagement")
    assert dados_presentes(tmp_path) is True


# -------------------------------------------------------------------- publicar


def test_publicar_envia_so_silver_e_gold(tmp_path):
    _tabela(tmp_path, "gold", "governor_engagement")
    _tabela(tmp_path, "silver", "posts_clean")
    cliente = ClienteFake()
    enviadas = publicar(tmp_path, CONFIG, cliente)
    assert enviadas == ["silver/posts_clean", "gold/governor_engagement"]
    pasta, padroes, _ = cliente.enviados[0]
    assert pasta == tmp_path
    assert padroes == PADROES_PUBLICACAO == ["silver/**", "gold/**"]


def test_publicar_recusa_sem_gold(tmp_path):
    _tabela(tmp_path, "silver", "posts_clean")
    cliente = ClienteFake()
    with pytest.raises(ErroHF, match="Gold"):
        publicar(tmp_path, CONFIG, cliente)
    assert cliente.enviados == []


# ---------------------------------------------------------------------- baixar


def test_baixar_pede_so_silver_e_gold(tmp_path):
    cliente = ClienteFake()
    baixar(tmp_path, CONFIG, cliente)
    assert cliente.baixados == [(tmp_path, ["silver/**", "gold/**"])]


# --------------------------------------------------------------- garantir_dados


def test_garantir_dados_local_nao_baixa(tmp_path):
    _tabela(tmp_path, "gold", "governor_engagement")
    chamadas = []
    assert garantir_dados(tmp_path, CONFIG, lambda d, c: chamadas.append(d)) == "local"
    assert chamadas == []


def test_garantir_dados_sem_configuracao_nao_faz_nada(tmp_path):
    chamadas = []
    estado = garantir_dados(tmp_path, None, lambda d, c: chamadas.append(d))
    assert estado == "sem_configuracao"
    assert chamadas == []


def test_garantir_dados_baixa_quando_falta_e_ha_configuracao(tmp_path):
    cliente = ClienteFake()
    estado = garantir_dados(tmp_path, CONFIG, lambda d, c: baixar(d, c, cliente))
    assert estado == "baixado"
    assert dados_presentes(tmp_path)


def test_garantir_dados_erro_nunca_vaza_o_token(tmp_path):
    cliente = ClienteFake(falha=RuntimeError(f"401 para o token {CONFIG.token}"))
    estado = garantir_dados(tmp_path, CONFIG, lambda d, c: baixar(d, c, cliente))
    assert estado.startswith("erro")
    assert CONFIG.token not in estado
    assert "***" in estado


def test_garantir_dados_erro_hf_e_repassado_como_estado(tmp_path):
    cliente = ClienteFake(
        falha=ErroHF("download do dataset falhou (RepositoryNotFoundError)")
    )
    estado = garantir_dados(tmp_path, CONFIG, lambda d, c: baixar(d, c, cliente))
    assert estado.startswith("erro: download do dataset falhou")


def test_garantir_dados_dataset_sem_gold_vira_erro(tmp_path):
    cliente = ClienteFake(cria_gold_ao_baixar=False)
    estado = garantir_dados(tmp_path, CONFIG, lambda d, c: baixar(d, c, cliente))
    assert estado.startswith("erro") and "Gold" in estado


# ------------------------------------------------- dashboard leve (sem NLP) --


def test_dashboard_nao_importa_a_pilha_de_nlp():
    """O deploy instala só `dashboard/requirements.txt`: nenhuma tela pode
    arrastar bertopic, scipy, torch ou o SDK do Gemini (ADR 0036)."""
    codigo = (
        "import importlib, pkgutil, sys, logging\n"
        "logging.disable(logging.CRITICAL)\n"
        "import dashboard.screens as s, dashboard.core as c\n"
        "for pkg in (s, c):\n"
        "    for m in pkgutil.iter_modules(pkg.__path__):\n"
        "        importlib.import_module(pkg.__name__ + '.' + m.name)\n"
        "pesados = ['bertopic', 'scipy', 'torch', 'sentence_transformers',\n"
        "           'transformers', 'sklearn', 'google.generativeai']\n"
        "print(','.join(m for m in pesados if m in sys.modules))\n"
    )
    saida = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert saida.returncode == 0, saida.stderr[-500:]
    assert saida.stdout.strip() == ""
