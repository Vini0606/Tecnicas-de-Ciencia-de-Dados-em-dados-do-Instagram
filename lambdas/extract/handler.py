import json
import os
import uuid

from apify_client import ApifyClient

from src.data_extract.bronze_writer import BronzeWriter
from src.data_extract.scraper import InstagramScraper, ScraperConfig

STORAGE_OPTIONS = {
    "AWS_REGION": os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    "AWS_S3_ALLOW_UNSAFE_RENAME": "true",
}


def handler(event, context):
    links = event.get("links", [])
    token = os.environ.get("APIFY_API_TOKEN")
    bucket = os.environ.get("S3_BUCKET")

    if not token or not bucket:
        return {"statusCode": 400, "body": "Missing APIFY_API_TOKEN or S3_BUCKET"}

    if not links:
        return {"statusCode": 400, "body": "Missing links in event"}

    run_id = event.get("run_id") or str(uuid.uuid4())

    scraper = InstagramScraper(
        client=ApifyClient(token),
        config=ScraperConfig(results_limit=int(os.environ.get("RESULTS_LIMIT", 30))),
    )

    profiles = scraper.scrape_profiles(links)
    posts = scraper.scrape_posts(links)
    reels = scraper.scrape_reels(links)

    bronze_prefix = os.environ.get("S3_BRONZE_PREFIX", "bronze/")
    bronze = BronzeWriter(
        bronze_profiles_path=f"s3://{bucket}/{bronze_prefix}instagram_profiles",
        bronze_posts_path=f"s3://{bucket}/{bronze_prefix}instagram_posts",
        bronze_reels_path=f"s3://{bucket}/{bronze_prefix}instagram_reels",
        storage_options=STORAGE_OPTIONS,
    )

    bronze.write_profiles(profiles, run_id=run_id)
    bronze.write_posts(posts, run_id=run_id)
    bronze.write_reels(reels, run_id=run_id)

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "run_id": run_id,
                "profiles": len(profiles),
                "posts": len(posts),
                "reels": len(reels),
            }
        ),
    }
