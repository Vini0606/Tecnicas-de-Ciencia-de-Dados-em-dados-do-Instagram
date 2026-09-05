"""
Roda o estágio determinístico de modelagem (PCA -> clustering -> sentimento
-> tópicos -> performance-por-post) sobre a Silver/Gold-engagement já
existentes, sem reprocessar Bronze/Silver/Gold-engagement. Ver ADR 0003.
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


def run(run_id: str | None = None, parent_run_id: str | None = None) -> str:
    repo = DeltaRepository(gold_dir=settings.GOLD_DIR, silver_dir=settings.SILVER_DIR)
    df_reels = repo.load_reels()
    df_comments = repo.load_comments()
    df_posts = repo.load_posts()
    df_engagement = repo.load_profiles()

    result = run_deterministic_modeling(
        df_reels,
        df_comments,
        df_posts,
        df_engagement,
        ModelingConfig(),
        run_id=run_id,
        parent_run_id=parent_run_id,
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
    parser.add_argument(
        "--parent-run-id",
        required=True,
        help=(
            "run_id da extracao/execucao de pipeline.py que gerou a Silver sendo usada aqui -- "
            "obrigatorio para rastreabilidade completa (dados -> modelo, ver "
            "scripts/inspect_runs.py --pipeline). A Silver pode ter dado de multiplas extracoes "
            "misturadas (overwrite por _run_id mais recente por linha), entao nao da pra inferir "
            "isso sozinho; se voce nao souber qual foi, rode "
            "'uv run python scripts/inspect_runs.py' para descobrir o run_id de extracao mais "
            "recente antes de rodar este script."
        ),
    )
    args = parser.parse_args()

    run_id = run(run_id=args.run_id, parent_run_id=args.parent_run_id)
    # Sem emoji: o console padrao do Windows usa cp1252 e levanta
    # UnicodeEncodeError ao imprimi-los.
    print(f"[OK] Modelagem deterministica concluida com run_id: {run_id}")
    print(f"[OK] Checkpoint salvo em: {settings.MODEL_CHECKPOINTS_DIR / run_id}")
