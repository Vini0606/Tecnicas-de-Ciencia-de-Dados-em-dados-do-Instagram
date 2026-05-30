import json
import os

from deltalake import DeltaTable

from src.features.gold.engagement_aggregator import EngagementAggregator

STORAGE_OPTIONS = {
    "AWS_REGION": os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    "AWS_S3_ALLOW_UNSAFE_RENAME": "true",
}


def handler(event, context):
    bucket = os.environ.get("S3_BUCKET", "")
    silver_pfx = os.environ.get("S3_SILVER_PREFIX", "silver/")
    gold_pfx = os.environ.get("S3_GOLD_PREFIX", "gold/")

    run_id = event.get("run_id")
    if not bucket:
        return {"statusCode": 400, "body": "Missing S3_BUCKET"}
    if not run_id:
        return {"statusCode": 400, "body": "Missing run_id in event"}

    silver_base = f"s3://{bucket}/{silver_pfx}"
    gold_base = f"s3://{bucket}/{gold_pfx}"

    df_profiles = DeltaTable(
        f"{silver_base}profiles_clean", storage_options=STORAGE_OPTIONS
    ).to_pandas()
    df_posts = DeltaTable(
        f"{silver_base}posts_clean", storage_options=STORAGE_OPTIONS
    ).to_pandas()
    df_reels = DeltaTable(
        f"{silver_base}reels_clean", storage_options=STORAGE_OPTIONS
    ).to_pandas()

    aggregator = EngagementAggregator()
    df_gold = aggregator.aggregate(df_profiles, df_posts, df_reels, run_id)
    aggregator.write(df_gold, f"{gold_base}governor_engagement")

    return {
        "statusCode": 200,
        "body": json.dumps({"run_id": run_id, "status": "gold_complete"}),
    }
