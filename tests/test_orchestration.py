import json
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
from deltalake import DeltaTable

from src.modeling.config import ClusterConfig, GeminiRefinerConfig, ModelingConfig
from src.modeling.orchestration import run_deterministic_modeling, refine_topics_with_gemini


def _df_reels():
    rng = np.random.default_rng(0)
    grupo_a = rng.normal(loc=(50, 500, 5000, 30), scale=1.0, size=(6, 4))
    grupo_b = rng.normal(loc=(5, 50, 500, 90), scale=1.0, size=(6, 4))
    dados = np.vstack([grupo_a, grupo_b])
    df = pd.DataFrame(
        dados, columns=["commentsCount", "likesCount", "videoPlayCount", "videoDuration"]
    )
    df["id"] = [f"reel_{i}" for i in range(len(df))]
    df["ownerUsername"] = "governador_teste"
    return df


def _df_comments():
    return pd.DataFrame(
        {
            "id_comment": ["c1", "c2", "c3"],
            "text": ["ótimo trabalho", "péssimo governo", "concordo com a proposta"],
        }
    )


def _fake_analyze_sentiment(df_comments, config):
    df = df_comments.copy()
    df["sentiment_label"] = "Positive"
    df["sentiment_score"] = 0.9
    return df


def _make_fake_model_topics(nome_provisorio, nome_refinado):
    def _fake_model_topics(docs, config, embedding_model=None):
        topic_model = MagicMock()
        topic_model.get_document_info.return_value = pd.DataFrame(
            {"Document": docs, "Topic": [0] * len(docs), "Name": [nome_refinado] * len(docs)}
        )
        document_info_provisorio = pd.DataFrame(
            {"Document": docs, "Topic": [0] * len(docs), "Name": [nome_provisorio] * len(docs)}
        )
        return topic_model, [0] * len(docs), np.zeros(len(docs)), document_info_provisorio

    return _fake_model_topics


def _fake_apply_gemini_refinement(topic_model, docs, config):
    return topic_model


def test_run_deterministic_modeling_grava_clusters_e_sentimento_com_mesmo_run_id(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "src.modeling.orchestration.analyze_sentiment", _fake_analyze_sentiment
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.model_topics",
        _make_fake_model_topics("0_provisorio", "0_refinado"),
    )

    config = ModelingConfig(
        cluster=ClusterConfig(max_evals_per_algo=10, random_state=42, max_n_clusters=5),
        gold_clusters_path=tmp_path / "governor_clusters",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )

    result = run_deterministic_modeling(_df_reels(), _df_comments(), config)

    clusters_out = DeltaTable(str(config.gold_clusters_path)).to_pandas()
    sentiment_out = DeltaTable(str(config.gold_sentiment_path)).to_pandas()

    assert len(clusters_out) == len(_df_reels())
    assert (clusters_out["_run_id"] == result.run_id).all()
    assert (sentiment_out["_run_id"] == result.run_id).all()
    assert (sentiment_out["Name"] == "0_provisorio").all()

    checkpoint_dir = config.checkpoints_dir / result.run_id
    assert (checkpoint_dir / "metadata.json").exists()
    assert (checkpoint_dir / "df_reels.parquet").exists()
    assert (checkpoint_dir / "df_comments.parquet").exists()
    assert (checkpoint_dir / "pca_model.joblib").exists()
    assert (checkpoint_dir / "cluster_model.joblib").exists()


def test_run_deterministic_modeling_grava_parent_run_id_como_primeira_linha_do_log(
    monkeypatch, tmp_path
):
    """Rastreabilidade completa (dados -> modelo, pedido do usuario) exige
    que quem abrir so o arquivo de log da modelagem, sem checar o
    checkpoint, ja saiba de qual execucao ela veio."""
    monkeypatch.setattr(
        "src.modeling.orchestration.analyze_sentiment", _fake_analyze_sentiment
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.model_topics",
        _make_fake_model_topics("0_provisorio", "0_refinado"),
    )

    config = ModelingConfig(
        cluster=ClusterConfig(max_evals_per_algo=10, random_state=42, max_n_clusters=5),
        gold_clusters_path=tmp_path / "governor_clusters",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )

    result = run_deterministic_modeling(
        _df_reels(), _df_comments(), config, parent_run_id="run_extracao_pai"
    )

    assert result.parent_run_id == "run_extracao_pai"

    log_path = config.logs_dir / result.run_id / "pipeline.log"
    primeira_linha = log_path.read_text(encoding="utf-8").splitlines()[0]
    assert "parent_run_id: run_extracao_pai" in primeira_linha

    metadata = json.loads(
        (config.checkpoints_dir / result.run_id / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["parent_run_id"] == "run_extracao_pai"


def test_refine_topics_with_gemini_so_reescreve_sentimento_com_run_id_novo(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "src.modeling.orchestration.analyze_sentiment", _fake_analyze_sentiment
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.model_topics",
        _make_fake_model_topics("0_provisorio", "0_refinado"),
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.apply_gemini_refinement", _fake_apply_gemini_refinement
    )

    config = ModelingConfig(
        cluster=ClusterConfig(max_evals_per_algo=10, random_state=42, max_n_clusters=5),
        gold_clusters_path=tmp_path / "governor_clusters",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )
    result = run_deterministic_modeling(_df_reels(), _df_comments(), config)

    gemini_config = GeminiRefinerConfig(
        api_key="fake-key", gold_sentiment_path=tmp_path / "governor_sentiment"
    )
    refinement = refine_topics_with_gemini(
        result.topic_model, result.docs, result.df_comments, gemini_config
    )

    assert refinement.run_id != result.run_id

    sentiment_out = DeltaTable(str(gemini_config.gold_sentiment_path)).to_pandas()
    clusters_out = DeltaTable(str(config.gold_clusters_path)).to_pandas()

    # A segunda escrita é overwrite: só o run_id do refinamento sobra em
    # governor_sentiment, com os rótulos finais.
    assert (sentiment_out["_run_id"] == refinement.run_id).all()
    assert (sentiment_out["Name"] == "0_refinado").all()

    # governor_clusters não é tocado pelo refinamento de tópicos.
    assert (clusters_out["_run_id"] == result.run_id).all()
