"""
Roda o cálculo de CMGR (crescimento mensal composto) e retenção de
sentimento positivo sobre o histórico já acumulado (ADR 0020, Ficha 7 /
issue #92).

Standalone de propósito -- diferente de `scripts/run_modeling.py`
(estágio determinístico) e de outros estágios pós-modelagem desta ADR
(NSM/Score ICE, Fichas 5/6), este módulo só lê `governor_engagement_history`
e `governor_sentiment_history` (tabelas append já existentes e alimentadas
independentemente desta issue) e não depende de nenhum outro estágio de
modelagem -- por isso não entra em `src/modeling/orchestration.py`. Isso
também evita competir pelo mesmo ponto de orquestração que as Fichas 5/6
(NSM e Score ICE), em desenvolvimento em paralelo.

*** LIMITAÇÃO EXPLÍCITA ***
Em 2026-09 o pipeline acumulou poucas execuções de modelagem -- o CMGR e a
retenção calculados aqui são ILUSTRATIVOS, não conclusivos (ver
`src/modeling/growth_history.py`). A tabela `governor_growth_metrics`
carrega essa ressalva explicitamente nas colunas `ilustrativo`/`nota` para
qualquer consumidor (dashboard, texto do TCC).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from config import settings
from src.features.gold.model_enricher import ModelEnricher
from src.modeling.growth_history import compute_growth_metrics
from src.repositories.delta_repository import DeltaRepository
from src.run_id import build_run_id


def run(run_id: str | None = None) -> str:
    run_id = build_run_id(run_id)
    repo = DeltaRepository(gold_dir=settings.GOLD_DIR, silver_dir=settings.SILVER_DIR)

    df_engagement_history = repo.load_engagement_history()
    df_sentiment_history = repo.load_sentiment_history()

    df_growth_metrics = compute_growth_metrics(df_engagement_history, df_sentiment_history)

    enricher = ModelEnricher()
    enricher.write_growth_metrics(df_growth_metrics, settings.GOLD_GROWTH_METRICS, run_id)

    n_ilustrativo = int(df_growth_metrics["ilustrativo"].sum())
    print(f"[OK] {len(df_growth_metrics)} perfis processados ({n_ilustrativo} ilustrativos)")
    return run_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Calcula CMGR e retencao de sentimento positivo sobre "
            "governor_engagement_history/governor_sentiment_history (ADR 0020, Ficha 7)."
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
    print(f"[OK] Calculo de CMGR/retencao concluido com run_id: {run_id}")
