"""
Roda o clustering de PERFIL de governador por Engajamento (Fase 2) sobre o
Gold `governor_engagement` já existente -- não reprocessa Bronze/Silver/
Gold-engagement. Distinto de `scripts/run_modeling.py`, que clusteriza reels.

Features: % ENGAJAMENTO, RECENCIA, FREQUENCIA -- métricas relativas/
comportamentais, não volume bruto (followersCount/commentsSum/likesSum
correlacionam quase só com tamanho de audiência, não com comportamento; ver
sessão de design da Fase 2).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from config import settings
from src.features.gold.model_enricher import ModelEnricher
from src.modeling.config import ClusterConfig
from src.modeling.profile_clustering import cluster_governor_profiles
from src.repositories.delta_repository import DeltaRepository
from src.run_id import build_run_id

FEATURE_COLUMNS = ["% ENGAJAMENTO", "RECENCIA", "FREQUENCIA"]

# Só 27 governadores -- o default de ClusterConfig.max_n_clusters (folgado o
# bastante para reels, na casa das centenas/milhares) permitiria clusters
# quase do tamanho da amostra. 6 já é generoso para 27 pontos.
MAX_N_CLUSTERS = 6


def run(run_id: str | None = None) -> str:
    run_id = build_run_id(run_id)
    repo = DeltaRepository(gold_dir=settings.GOLD_DIR, silver_dir=settings.SILVER_DIR)
    df_profiles = repo.load_profiles()

    config = ClusterConfig(feature_columns=FEATURE_COLUMNS, max_n_clusters=MAX_N_CLUSTERS)
    df_clustered, model, cluster_config, score, algo_name = cluster_governor_profiles(
        df_profiles, config
    )

    enricher = ModelEnricher()
    enricher.write_profile_clusters_engagement(
        df_clustered, settings.GOLD_PROFILE_CLUSTERS_ENGAGEMENT, run_id
    )

    print(f"[OK] Algoritmo vencedor: {algo_name} (score CVI combinado: {score:.4f})")
    print(f"[OK] Distribuição de clusters:\n{df_clustered['Clusters (AutoClusterHPO)'].value_counts().sort_index()}")
    return run_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Roda o clustering de perfil de governador por Engajamento (Fase 2)."
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
    print(f"[OK] Clustering de perfil por engajamento concluido com run_id: {run_id}")
