"""
Calcula o Escore composto (Scorecard) dos governadores (ADR 0030, issue #184)
sobre a Silver/Gold ja existentes e grava `governor_scorecard`.

Standalone, mesmo padrao de `scripts/run_growth_metrics.py`: o estagio tambem
roda dentro de `src.modeling.orchestration.run_deterministic_modeling`
(`coleta.py coletar --modelar` / `scripts/run_modeling.py`); este script serve
para recalcular so a tabela, sem repetir toda a modelagem.

Leitura sempre via `DeltaRepository` (somente leitura); escrita por
`GovernorScorecardScorer.write` (overwrite, schema validado).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from config import settings
from src.modeling.governor_scorecard import GovernorScorecardScorer
from src.repositories.delta_repository import DeltaRepository
from src.run_id import build_run_id


def run(run_id: str | None = None) -> str:
    run_id = build_run_id(run_id)
    repo = DeltaRepository(gold_dir=settings.GOLD_DIR, silver_dir=settings.SILVER_DIR)

    scorer = GovernorScorecardScorer()
    df_scorecard = scorer.score(
        repo.load_profiles(),
        repo.load_reels(),
        repo.load_posts(),
        repo.load_comments(),
    )
    scorer.write(df_scorecard, settings.GOLD_GOVERNOR_SCORECARD, run_id)

    n_pendentes = int(df_scorecard["consistencia_pendente"].sum())
    escores = df_scorecard["escore"].dropna()
    faixa = f"{escores.min():.1f} a {escores.max():.1f}" if len(escores) else "n/d"
    print(
        f"[OK] {len(df_scorecard)} perfis processados "
        f"({n_pendentes} com Consistencia pendente; faixa de escores: {faixa})"
    )
    return run_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Calcula o Escore composto (Scorecard) dos governadores (ADR 0030)."
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
    print(f"[OK] Escore composto concluido com run_id: {run_id}")
