"""Testes da publicação/download das tabelas do dashboard no HF (ADR 0036).

Nunca usam a rede: o cliente HF é um fake injetado.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from src.dados_hf import ClienteHFReal, ErroHF
from src.publicacao_hf import (
    PADROES_PUBLICACAO,
    ConfigHF,
    baixar,
    ler_manifesto,
    configuracao_hf,
    dados_presentes,
    garantir_dados,
)

CONFIG = ConfigHF(token="hf_segredo_123", repo="usuario/dados-dashboard")


def _tabela(base: Path, camada: str, nome: str) -> None:
    (base / camada / nome / "_delta_log").mkdir(parents=True)


class ClienteFake:
    def __init__(
        self, cria_gold_ao_baixar: bool = True, falha: Exception | None = None
    ):
        self.baixados: list[tuple[Path, list[str]]] = []
        self.revisoes: list[str | None] = []
        self._cria = cria_gold_ao_baixar
        self._falha = falha

    def listar_arquivos(self, revisao=None):
        return []

    def baixar(self, pasta, padroes, revisao=None):
        if self._falha:
            raise self._falha
        self.baixados.append((pasta, padroes))
        self.revisoes.append(revisao)
        if self._cria:
            _tabela(Path(pasta), "gold", "governor_engagement")


# --------------------------------------------------------------- configuração


def test_configuracao_usa_a_primeira_fonte_completa():
    env = {"HF_TOKEN": "t"}  # sem repositório: incompleta
    secrets = {"HF_TOKEN": "t2", "HF_DATASET_REPO_PUBLICACAO": "u/d"}
    assert configuracao_hf(env, secrets) == ConfigHF(token="t2", repo="u/d")


def test_configuracao_usa_o_dataset_padrao_sem_dataset_de_publicacao():
    env = {"HF_TOKEN": "t", "HF_DATASET_REPO": "u/landing-bronze"}
    assert configuracao_hf(env) == ConfigHF(token="t", repo="u/landing-bronze")


def test_configuracao_dataset_de_publicacao_tem_prioridade_sobre_o_padrao():
    env = {
        "HF_TOKEN": "t",
        "HF_DATASET_REPO": "u/landing-bronze",
        "HF_DATASET_REPO_PUBLICACAO": "u/dashboard",
    }
    assert configuracao_hf(env) == ConfigHF(token="t", repo="u/dashboard")


def test_configuracao_none_sem_token_ou_sem_repositorio():
    assert configuracao_hf({}, None) is None
    assert configuracao_hf({"HF_TOKEN": "t"}) is None
    assert configuracao_hf({"HF_DATASET_REPO_PUBLICACAO": "u/d"}) is None
    assert (
        configuracao_hf({"HF_TOKEN": "  ", "HF_DATASET_REPO_PUBLICACAO": "u/d"}) is None
    )


# --------------------------------------------------------------------- tabelas


def test_dados_presentes_depende_do_gold_de_engajamento(tmp_path):
    assert dados_presentes(tmp_path) is False
    _tabela(tmp_path, "gold", "governor_nsm")
    assert dados_presentes(tmp_path) is False
    _tabela(tmp_path, "gold", "governor_engagement")
    assert dados_presentes(tmp_path) is True


# ---------------------------------------------------------------------- baixar


def test_cliente_real_nao_vaza_token_em_falha_de_download(monkeypatch):
    import huggingface_hub

    def quebrado(*a, **k):
        raise RuntimeError(f"401 Unauthorized: Bearer {CONFIG.token}")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", quebrado)
    with pytest.raises(ErroHF) as exc:
        ClienteHFReal(CONFIG.repo, CONFIG.token).baixar(Path("x"), ["gold/**"])
    assert CONFIG.token not in str(exc.value) and CONFIG.token not in repr(exc.value.__cause__)


def test_baixar_pede_so_silver_e_gold(tmp_path):
    cliente = ClienteFake()
    baixar(tmp_path, CONFIG, cliente)
    assert cliente.baixados == [(tmp_path, ["silver/**", "gold/**", "manifesto.json"])]


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


# -------------------------------------------------------------------- revisao


def test_configuracao_le_a_revisao_opcional():
    env = {"HF_TOKEN": "t", "HF_DATASET_REPO": "u/d", "HF_DATASET_REVISAO": " v1 "}
    assert configuracao_hf(env) == ConfigHF(token="t", repo="u/d", revisao="v1")


def test_configuracao_sem_revisao_usa_a_main():
    cfg = configuracao_hf({"HF_TOKEN": "t", "HF_DATASET_REPO": "u/d"})
    assert cfg is not None and cfg.revisao is None
    cfg = configuracao_hf({"HF_TOKEN": "t", "HF_DATASET_REPO": "u/d", "HF_DATASET_REVISAO": "  "})
    assert cfg is not None and cfg.revisao is None


def test_baixar_sem_revisao_pede_a_main(tmp_path):
    cliente = ClienteFake()
    baixar(tmp_path, CONFIG, cliente)
    assert cliente.revisoes == [None]


def test_baixar_com_revisao_repassa_a_tag_ou_commit(tmp_path):
    cliente = ClienteFake()
    baixar(tmp_path, ConfigHF(token="t", repo="u/d", revisao="coleta_x"), cliente)
    assert cliente.revisoes == ["coleta_x"]
    assert not any("bronze" in p or "landing" in p for p in cliente.baixados[0][1])


# ------------------------------------------------------------------ manifesto


def test_ler_manifesto_devolve_none_se_ausente_ou_invalido(tmp_path):
    assert ler_manifesto(tmp_path) is None
    (tmp_path / "manifesto.json").write_text("{nao e json", encoding="utf-8")
    assert ler_manifesto(tmp_path) is None
    (tmp_path / "manifesto.json").write_text('{"x": 1}', encoding="utf-8")
    assert ler_manifesto(tmp_path) is None  # fora do esquema


def test_ler_manifesto_valido(tmp_path):
    from datetime import date, datetime

    from src.coleta.manifesto import escrever_manifesto, gerar_manifesto
    from src.coleta.recorte import Recorte, gerar_tag

    recorte = Recorte(dias=30, teto=50)
    tag = gerar_tag(recorte, date(2026, 10, 1))
    m = gerar_manifesto(
        tmp_path,
        tag=tag,
        recorte=recorte,
        extraido_em=datetime(2026, 10, 1, 12, 0),
        versao_codigo="abc123",
    )
    escrever_manifesto(tmp_path, m)
    assert ler_manifesto(tmp_path)["identidade"]["tag"] == tag
