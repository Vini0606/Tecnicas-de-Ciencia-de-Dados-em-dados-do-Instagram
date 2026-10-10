"""Lambda de reconstrucao: tag do HF -> Bronze, Silver e Gold (ADR 0039, issue #253).

HF falso em memoria e destino em pasta local: nenhuma rede, nenhum custo."""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from deltalake import DeltaTable, write_deltalake

import lambdas.rebuild.handler as rebuild_handler
from src.coleta.coletar import coletar
from src.coleta.hf import publicar
from src.coleta.recorte import Recorte
from test_coleta_coletar import AGORA, HOJE, LINK, _governadores, _ScraperFalso
from test_coleta_hf import ClienteFake

TAG = "coleta_2026-10-09_ultimos-90d_teto-250"
TABELAS = [
    "bronze/instagram_profiles",
    "bronze/instagram_posts",
    "bronze/instagram_reels",
    "silver/profiles_clean",
    "silver/posts_clean",
    "silver/reels_clean",
    "silver/comments_clean",
    "silver/governors_metadata",
    "gold/governor_engagement",
    "gold/governor_engagement_history",
]


@pytest.fixture
def cliente_hf(tmp_path):
    """HF falso com uma Coleta real (gerada com Apify falsa) publicada sob a tag."""
    snap = tmp_path / "snap"
    coletar(
        Recorte(dias=90, teto=250),
        snap,
        scraper=_ScraperFalso(),
        links=[LINK],
        governor_usernames=["gov_a"],
        df_governadores=_governadores(),
        confirmar=lambda custo: True,
        hoje=HOJE,
        agora=AGORA,
        run_id="run_coleta",
    )
    # Tabela Gold "pesada" ja calculada na Coleta: deve ser copiada, nao recalculada.
    write_deltalake(str(snap / "gold" / "governor_clusters_reels"), pd.DataFrame({"id": ["r1"], "cluster": [0]}))
    cliente = ClienteFake()
    resultado = publicar(snap, cliente=cliente, confirmar=lambda plano: True)
    assert resultado.tag == TAG
    return cliente


def _linhas(base: Path, tabela: str) -> int:
    return len(DeltaTable(str(base / tabela)).to_pandas())


def test_handler_reconstroi_bronze_silver_e_gold_a_partir_da_tag(tmp_path, monkeypatch, cliente_hf):
    destino = tmp_path / "s3_falso"
    monkeypatch.setenv("DESTINO_URI", str(destino))
    monkeypatch.setattr(rebuild_handler, "_criar_cliente", lambda: cliente_hf)

    resposta = rebuild_handler.handler({"tag": TAG, "run_id": "run_rebuild"}, None)

    assert resposta["statusCode"] == 200, resposta
    corpo = json.loads(resposta["body"])
    assert corpo["tag"] == TAG and corpo["status"] == "rebuild_complete"
    for tabela in TABELAS:
        assert _linhas(destino, tabela) >= 1, tabela
    # Gold de engajamento foi derivado agora (run_id novo); tabela modelada foi copiada
    gold = DeltaTable(str(destino / "gold" / "governor_engagement")).to_pandas()
    assert set(gold["_run_id"]) == {"run_rebuild"}
    assert _linhas(destino, "gold/governor_clusters_reels") == 1
    assert "gold/governor_clusters_reels" in corpo["copiadas"]


def test_reconstruir_duas_vezes_e_idempotente(tmp_path, monkeypatch, cliente_hf):
    destino = tmp_path / "s3_falso"
    monkeypatch.setenv("DESTINO_URI", str(destino))
    monkeypatch.setattr(rebuild_handler, "_criar_cliente", lambda: cliente_hf)

    rebuild_handler.handler({"tag": TAG}, None)
    antes = {t: _linhas(destino, t) for t in TABELAS}
    rebuild_handler.handler({"tag": TAG}, None)

    assert {t: _linhas(destino, t) for t in TABELAS} == antes


def test_tag_inexistente_devolve_422_sem_escrever_nada(tmp_path, monkeypatch, cliente_hf):
    destino = tmp_path / "s3_falso"
    monkeypatch.setenv("DESTINO_URI", str(destino))
    monkeypatch.setattr(rebuild_handler, "_criar_cliente", lambda: cliente_hf)

    resposta = rebuild_handler.handler({"tag": "coleta_2020-01-01"}, None)

    assert resposta["statusCode"] == 422
    assert not destino.exists()


def test_evento_sem_tag_ou_sem_destino_devolve_400(monkeypatch):
    monkeypatch.delenv("DESTINO_URI", raising=False)
    monkeypatch.delenv("S3_BUCKET", raising=False)
    assert rebuild_handler.handler({}, None)["statusCode"] == 400
    assert rebuild_handler.handler({"tag": TAG}, None)["statusCode"] == 400


def test_destino_s3_vem_do_bucket_e_do_prefixo(monkeypatch, cliente_hf):
    visto = {}

    def falso(tag, destino, **kw):
        visto["destino"] = destino
        return {"tag": tag, "run_id": "r", "governadores": 0, "copiadas": []}

    monkeypatch.delenv("DESTINO_URI", raising=False)
    monkeypatch.setenv("S3_BUCKET", "meu-bucket")
    monkeypatch.setenv("S3_BASE_PREFIX", "dados/")
    monkeypatch.setattr(rebuild_handler, "reconstruir", falso)
    monkeypatch.setattr(rebuild_handler, "_criar_cliente", lambda: cliente_hf)

    assert rebuild_handler.handler({"tag": TAG}, None)["statusCode"] == 200
    assert visto["destino"] == "s3://meu-bucket/dados/"


def test_handler_nao_importa_apify_nem_modelagem_pesada():
    codigo = (
        "import sys, lambdas.rebuild.handler\n"
        "proibidos = ('apify_client', 'sklearn', 'bertopic', 'torch', 'transformers', 'sentence_transformers')\n"
        "achados = [m for m in proibidos if m in sys.modules]\n"
        "assert not achados, achados\n"
        "assert not any(m.startswith('src.modeling') for m in sys.modules)\n"
    )
    resultado = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
    assert resultado.returncode == 0, resultado.stderr


def test_requirements_da_imagem_sem_apify_nem_modelagem():
    texto = (Path(__file__).parent.parent / "lambdas" / "rebuild" / "requirements.txt").read_text().lower()
    for proibido in ("apify", "bertopic", "torch", "scikit", "sentence", "transformers", "umap", "hdbscan"):
        assert proibido not in texto
