import json
import os

from src.data_extract.bronze_writer import BronzeWriter
from src.features.silver.comment_cleaner import CommentCleaner
from src.features.silver.post_cleaner import PostCleaner
from src.features.silver.profile_cleaner import ProfileCleaner

STORAGE_OPTIONS = {
    "AWS_REGION": os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    "AWS_S3_ALLOW_UNSAFE_RENAME": "true",
}


def handler(event, context):
    bucket = os.environ.get("S3_BUCKET", "")
    bronze_pfx = os.environ.get("S3_BRONZE_PREFIX", "bronze/")
    silver_pfx = os.environ.get("S3_SILVER_PREFIX", "silver/")

    run_id = event.get("run_id")
    if not bucket:
        return {"statusCode": 400, "body": "Missing S3_BUCKET"}
    if not run_id:
        return {"statusCode": 400, "body": "Missing run_id in event"}

    bronze = BronzeWriter(
        bronze_profiles_path=f"s3://{bucket}/{bronze_pfx}instagram_profiles",
        bronze_posts_path=f"s3://{bucket}/{bronze_pfx}instagram_posts",
        bronze_reels_path=f"s3://{bucket}/{bronze_pfx}instagram_reels",
        storage_options=STORAGE_OPTIONS,
    )

    df_profiles_raw = bronze.get_latest_profiles()
    df_posts_raw = bronze.get_latest_posts()
    df_reels_raw = bronze.get_latest_reels()

    profile_cleaner = ProfileCleaner()
    post_cleaner = PostCleaner()
    comment_cleaner = CommentCleaner()

    silver_base = f"s3://{bucket}/{silver_pfx}"

    profile_cleaner.write(
        profile_cleaner.clean(df_profiles_raw, run_id),
        f"{silver_base}profiles_clean",
    )
    post_cleaner.write_posts(
        post_cleaner.clean_posts(df_posts_raw),
        f"{silver_base}posts_clean",
    )
    post_cleaner.write_reels(
        post_cleaner.clean_reels(df_reels_raw),
        f"{silver_base}reels_clean",
    )
    comment_cleaner.write(
        comment_cleaner.clean(df_reels_raw),
        f"{silver_base}comments_clean",
    )

    return {
        "statusCode": 200,
        "body": json.dumps({"run_id": run_id, "status": "silver_complete"}),
    }
