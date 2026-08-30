import json
import os

from deltalake import DeltaTable

from src.features.gold.model_enricher import ModelEnricher
from src.modeling.config import ClusterConfig
from src.modeling.profile_clustering import cluster_governor_profiles

STORAGE_OPTIONS = {
    "AWS_REGION": os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    "AWS_S3_ALLOW_UNSAFE_RENAME": "true",
}

# Mesmas features/limite usados em scripts/run_profile_clustering_engagement.py
# (validado localmente antes desta Lambda existir) -- ver sessão de design da
# Fase 2: métricas relativas/comportamentais, não volume bruto; max_n_clusters
# pequeno porque só há 27 governadores.
FEATURE_COLUMNS = ["% ENGAJAMENTO", "RECENCIA", "FREQUENCIA"]
MAX_N_CLUSTERS = 6


def handler(event, context):
    bucket = os.environ.get("S3_BUCKET", "")
    gold_pfx = os.environ.get("S3_GOLD_PREFIX", "gold/")

    run_id = event.get("run_id")
    if not bucket:
        return {"statusCode": 400, "body": "Missing S3_BUCKET"}
    if not run_id:
        return {"statusCode": 400, "body": "Missing run_id in event"}

    gold_base = f"s3://{bucket}/{gold_pfx}"

    df_profiles = DeltaTable(
        f"{gold_base}governor_engagement", storage_options=STORAGE_OPTIONS
    ).to_pandas()

    config = ClusterConfig(feature_columns=FEATURE_COLUMNS, max_n_clusters=MAX_N_CLUSTERS)
    df_clustered, _model, _cluster_config, _score, _algo_name = cluster_governor_profiles(
        df_profiles, config
    )

    enricher = ModelEnricher()
    enricher.write_profile_clusters_engagement(
        df_clustered, f"{gold_base}governor_profile_clusters_engagement", run_id
    )

    return {
        "statusCode": 200,
        "body": json.dumps({"run_id": run_id, "status": "profile_clusters_engagement_complete"}),
    }
