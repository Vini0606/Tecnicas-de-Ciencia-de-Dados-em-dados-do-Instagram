"""
Roda o estágio determinístico de modelagem (PCA -> clustering -> sentimento
-> tópicos) sobre a Silver já existente, sem reprocessar Bronze/Silver/
Gold-engagement. Ver ADR 0003.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from config import settings
from src.modeling.config import ModelingConfig
from src.modeling.orchestration import run_deterministic_modeling
from src.repositories.delta_repository import DeltaRepository


def run(run_id: str | None = None) -> str:
    repo = DeltaRepository(gold_dir=settings.GOLD_DIR, silver_dir=settings.SILVER_DIR)
    df_reels = repo.load_reels()
    df_comments = repo.load_comments()

    result = run_deterministic_modeling(
        df_reels, df_comments, ModelingConfig(), run_id=run_id
    )
    return result.run_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Roda o estagio deterministico de modelagem "
            "(PCA, clustering, sentimento, topicos) sobre a Silver existente."
        )
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="run_id a usar para esta execucao (default: gerado automaticamente).",
    )
    args = parser.parse_args()

    run_id = run(run_id=args.run_id)
    # Sem emoji: o console padrao do Windows usa cp1252 e levanta
    # UnicodeEncodeError ao imprimi-los.
    print(f"[OK] Modelagem deterministica concluida com run_id: {run_id}")
    print(f"[OK] Checkpoint salvo em: {settings.MODEL_CHECKPOINTS_DIR / run_id}")
