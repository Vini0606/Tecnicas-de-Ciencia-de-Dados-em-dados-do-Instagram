"""Persistência local do checkpoint do estágio determinístico (ver ADR 0003)"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd
from bertopic import BERTopic

from config import settings


@dataclass
class DeterministicCheckpoint:
    topic_model: BERTopic
    df_comments: pd.DataFrame
    df_reels: pd.DataFrame
    docs: list[str]
    pca_model: object
    pca_feature_columns: list[str]
    cluster_model: object
    cluster_config: dict | None
    cluster_score: float
    cluster_algo_name: str | None
    embedding_model_name: str
    parent_run_id: str | None = None


def save_checkpoint(
    run_id: str,
    *,
    topic_model: BERTopic,
    df_comments: pd.DataFrame,
    df_reels: pd.DataFrame,
    pca_model: object,
    pca_feature_columns: list[str],
    cluster_model: object,
    cluster_config: dict | None,
    cluster_score: float,
    cluster_algo_name: str | None,
    embedding_model_name: str,
    checkpoints_dir: Path | None = None,
    parent_run_id: str | None = None,
) -> Path:
    """Grava o checkpoint de `run_id` em `<checkpoints_dir>/<run_id>/`.

    `df_reels` (com `PC1_Engajamento_videoPlay`/`PC2_videoDuration`/
    `Clusters (AutoClusterHPO)`) é persistido porque `governor_clusters` no
    Gold só guarda `cluster_label`, não as coordenadas de PCA — sem isso o
    notebook não conseguiria reproduzir o gráfico de validação do cluster
    sem reprocessar a Silver.

    O modelo de embedding não é reserializado junto do `topic_model`
    (`save_embedding_model=False`) — é grande, compartilhado entre execuções
    e já reproduzível a partir do nome (`embedding_model_name`), então
    duplicá-lo a cada checkpoint só desperdiçaria disco.

    `parent_run_id`, se informado, é o `run_id` da execução (extração ou
    invocação de `pipeline.py`) que disparou esta modelagem -- puramente
    informativo, gravado só em `metadata.json`. Não substitui nem se mistura
    com o `run_id` da própria modelagem (ADR 0001: cada estágio mantém seu
    `run_id` imutável); serve só pra reconstruir depois qual pipeline
    completo gerou qual checkpoint (ver `scripts/inspect_runs.py`)."""
    checkpoint_dir = (checkpoints_dir or settings.MODEL_CHECKPOINTS_DIR) / run_id
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    topic_model.save(
        str(checkpoint_dir / "topic_model"),
        serialization="pickle",
        save_embedding_model=False,
    )
    df_comments.to_parquet(checkpoint_dir / "df_comments.parquet", index=False)
    # 'model'/'config' (de cluster_reels) carregam objeto sklearn/dict cru
    # broadcast em toda linha -- não são serializáveis em parquet e já
    # ficam redundantes com cluster_model.joblib/metadata.json abaixo.
    df_reels.drop(columns=["model", "config"], errors="ignore").to_parquet(
        checkpoint_dir / "df_reels.parquet", index=False
    )
    joblib.dump(pca_model, checkpoint_dir / "pca_model.joblib")
    joblib.dump(cluster_model, checkpoint_dir / "cluster_model.joblib")

    metadata = {
        "cluster_config": cluster_config,
        "cluster_score": cluster_score,
        "cluster_algo_name": cluster_algo_name,
        "embedding_model_name": embedding_model_name,
        "pca_feature_columns": pca_feature_columns,
        "parent_run_id": parent_run_id,
    }
    (checkpoint_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return checkpoint_dir


def load_checkpoint(
    run_id: str, checkpoints_dir: Path | None = None
) -> DeterministicCheckpoint:
    """Carrega o checkpoint de `run_id`. `docs` é derivado de
    `df_comments['text_demojized']`, não persistido à parte — evita os dois
    artefatos dessincronizarem."""
    checkpoint_dir = (checkpoints_dir or settings.MODEL_CHECKPOINTS_DIR) / run_id
    if not checkpoint_dir.exists():
        raise FileNotFoundError(
            f"Checkpoint não encontrado para run_id={run_id!r} em {checkpoint_dir}"
        )

    metadata = json.loads((checkpoint_dir / "metadata.json").read_text(encoding="utf-8"))
    topic_model = BERTopic.load(
        str(checkpoint_dir / "topic_model"),
        embedding_model=metadata["embedding_model_name"],
    )
    df_comments = pd.read_parquet(checkpoint_dir / "df_comments.parquet")
    df_reels = pd.read_parquet(checkpoint_dir / "df_reels.parquet")
    docs = df_comments["text_demojized"].tolist()
    pca_model = joblib.load(checkpoint_dir / "pca_model.joblib")
    cluster_model = joblib.load(checkpoint_dir / "cluster_model.joblib")

    return DeterministicCheckpoint(
        topic_model=topic_model,
        df_comments=df_comments,
        df_reels=df_reels,
        docs=docs,
        pca_model=pca_model,
        pca_feature_columns=metadata["pca_feature_columns"],
        cluster_model=cluster_model,
        cluster_config=metadata["cluster_config"],
        cluster_score=metadata["cluster_score"],
        cluster_algo_name=metadata["cluster_algo_name"],
        embedding_model_name=metadata["embedding_model_name"],
        # .get() -- checkpoints gravados antes deste campo existir nao tem
        # a chave no metadata.json.
        parent_run_id=metadata.get("parent_run_id"),
    )
