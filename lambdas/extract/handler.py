import json
import os
import uuid

from apify_client import ApifyClient

from src.data_extract.bronze_writer import BronzeWriter
from src.data_extract.ingestion import extract_and_land
from src.data_extract.scraper import InstagramScraper, ScraperConfig

STORAGE_OPTIONS = {
    "AWS_REGION": os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    "AWS_S3_ALLOW_UNSAFE_RENAME": "true",
}

# Landing zone ainda local/efemera (o /tmp gravavel da Lambda) -- suporte a
# S3 para a landing zone e explicitamente fora de escopo ate a infra AWS ser
# de fato aplicada (ver ADR 0011 e docs/agents -- LANDING_DIR pode apontar
# para s3://.../landing/ no futuro sem mudar `extract_and_land`).
LANDING_DIR = os.environ.get("LANDING_DIR", "/tmp/landing")


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

    bronze_prefix = os.environ.get("S3_BRONZE_PREFIX", "bronze/")
    bronze = BronzeWriter(
        bronze_profiles_path=f"s3://{bucket}/{bronze_prefix}instagram_profiles",
        bronze_posts_path=f"s3://{bucket}/{bronze_prefix}instagram_posts",
        bronze_reels_path=f"s3://{bucket}/{bronze_prefix}instagram_reels",
        storage_options=STORAGE_OPTIONS,
    )

    result = extract_and_land(scraper, bronze, LANDING_DIR, links, run_id=run_id)

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "run_id": run_id,
                "profiles": len(result["profiles"]),
                "posts": len(result["posts"]),
                "reels": len(result["reels"]),
            }
        ),
    }
