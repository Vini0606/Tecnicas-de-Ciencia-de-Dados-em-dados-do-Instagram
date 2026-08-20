"""
Refina os rótulos de tópico de um checkpoint já gerado por `run_modeling.py`,
via Gemini (GeminiDocsRefiner). Etapa manual e de revisão humana -- decida
quando rodar depois de inspecionar os resultados provisórios em
`governor_sentiment`. Ver ADR 0003.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.modeling.checkpoint import load_checkpoint, save_checkpoint
from src.modeling.config import GeminiRefinerConfig
from src.modeling.orchestration import refine_topics_with_gemini


def run(run_id: str) -> str:
    checkpoint = load_checkpoint(run_id)

    api_key = os.getenv("API_GEMINI")
    if not api_key:
        raise ValueError("API_GEMINI nao definida no .env.")

    config = GeminiRefinerConfig(api_key=api_key)
    refinement = refine_topics_with_gemini(
        checkpoint.topic_model, checkpoint.docs, checkpoint.df_comments, config
    )

    # Reescreve o checkpoint em run_id (nao no run_id novo do refinamento):
    # sem isso, o topic_model salvo em disco ficaria com os rotulos
    # provisorios do estagio deterministico para sempre, e o notebook 03
    # mostraria labels desatualizados mesmo depois do refinamento rodar.
    save_checkpoint(
        run_id,
        topic_model=refinement.topic_model,
        df_comments=refinement.df_comments,
        df_reels=checkpoint.df_reels,
        pca_model=checkpoint.pca_model,
        pca_feature_columns=checkpoint.pca_feature_columns,
        cluster_model=checkpoint.cluster_model,
        cluster_config=checkpoint.cluster_config,
        cluster_score=checkpoint.cluster_score,
        cluster_algo_name=checkpoint.cluster_algo_name,
        embedding_model_name=checkpoint.embedding_model_name,
    )

    return refinement.run_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Refina os rotulos de topico de um checkpoint via Gemini "
            "(etapa manual, ver ADR 0003)."
        )
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="run_id do checkpoint gerado por run_modeling.py.",
    )
    args = parser.parse_args()

    refinement_run_id = run(run_id=args.run_id)
    # Sem emoji: o console padrao do Windows usa cp1252 e levanta
    # UnicodeEncodeError ao imprimi-los.
    print(f"[OK] Refinamento via Gemini concluido com run_id: {refinement_run_id}")
