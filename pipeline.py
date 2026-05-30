import os
import uuid
from datetime import datetime

from apify_client import ApifyClient
from dotenv import load_dotenv

from config import settings
from src.data_extract.bronze_writer import BronzeWriter
from src.data_extract.readers import JsonDataReader
from src.data_extract.scraper import InstagramScraper, ScraperConfig
from src.features.gold.engagement_aggregator import EngagementAggregator
from src.features.silver.comment_cleaner import CommentCleaner
from src.features.silver.post_cleaner import PostCleaner
from src.features.silver.profile_cleaner import ProfileCleaner


def _bronze_has_data(bronze: BronzeWriter) -> bool:
    try:
        df = bronze.get_latest_profiles()
        return not df.empty
    except Exception:
        return False


def _build_run_id(run_id: str | None = None) -> str:
    if run_id:
        return run_id
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{uuid.uuid4().hex[:8]}"


def _raw_has_data() -> bool:
    return all(
        [
            settings.PROFILES_JSON.exists(),
            settings.POSTS_JSON.exists(),
            settings.REELS_JSON.exists(),
        ]
    )


def _load_raw_data(reader: JsonDataReader):
    df_profiles = reader.read(settings.PROFILES_JSON)
    df_posts = reader.read(settings.POSTS_JSON)
    df_reels = reader.read(settings.REELS_JSON)
    return df_profiles, df_posts, df_reels


def run_medallion_pipeline(
    apify_api_token: str,
    links: list[str],
    results_limit: int = 30,
    run_id: str | None = None,
    force_extract: bool = False,
) -> str:
    run_id = _build_run_id(run_id)

    bronze = BronzeWriter(
        bronze_profiles_path=settings.BRONZE_PROFILES,
        bronze_posts_path=settings.BRONZE_POSTS,
        bronze_reels_path=settings.BRONZE_REELS,
    )
    reader = JsonDataReader()

    try:
        if not force_extract and _bronze_has_data(bronze):
            df_profiles = bronze.get_latest_profiles()
            df_posts = bronze.get_latest_posts()
            df_reels = bronze.get_latest_reels()
        elif not force_extract and _raw_has_data():
            print(
                "[1/3] BRONZE: Usando dados JSON locais existentes e migrando para Bronze..."
            )
            df_profiles, df_posts, df_reels = _load_raw_data(reader)
            bronze.write_profiles(df_profiles.to_dict(orient="records"), run_id=run_id)
            bronze.write_posts(df_posts.to_dict(orient="records"), run_id=run_id)
            bronze.write_reels(df_reels.to_dict(orient="records"), run_id=run_id)
        else:
            if not apify_api_token:
                raise ValueError(
                    "APIFY_API_TOKEN não fornecido e não há dados brutos locais."
                )
            print("[1/3] BRONZE: Extraindo dados brutos...")
            scraper = InstagramScraper(
                client=ApifyClient(apify_api_token),
                config=ScraperConfig(results_limit=results_limit),
            )
            profiles = scraper.scrape_profiles(links)
            posts = scraper.scrape_posts(links)
            reels = scraper.scrape_reels(links)

            bronze.write_profiles(profiles, run_id=run_id)
            bronze.write_posts(posts, run_id=run_id)
            bronze.write_reels(reels, run_id=run_id)

            df_profiles = bronze.get_latest_profiles()
            df_posts = bronze.get_latest_posts()
            df_reels = bronze.get_latest_reels()
    except Exception as e:
        raise RuntimeError(f"[BRONZE] Falha na ingestão de dados brutos: {e}") from e

    try:
        print("[2/3] SILVER: Limpando e conformando dados...")
        profile_cleaner = ProfileCleaner()
        post_cleaner = PostCleaner()
        comment_cleaner = CommentCleaner()

        df_profiles_silver = profile_cleaner.clean(df_profiles, run_id)
        df_posts_silver = post_cleaner.clean_posts(df_posts)
        df_reels_silver = post_cleaner.clean_reels(df_reels)
        df_comments_silver = comment_cleaner.clean(df_reels)

        profile_cleaner.write(df_profiles_silver, settings.SILVER_PROFILES)
        post_cleaner.write_posts(df_posts_silver, settings.SILVER_POSTS)
        post_cleaner.write_reels(df_reels_silver, settings.SILVER_REELS)
        comment_cleaner.write(df_comments_silver, settings.SILVER_COMMENTS)
    except Exception as e:
        raise RuntimeError(
            f"[SILVER] Falha na limpeza e conformação dos dados: {e}"
        ) from e

    try:
        print("[3/3] GOLD: Agregando métricas de engajamento...")
        aggregator = EngagementAggregator()
        df_gold = aggregator.aggregate(
            df_profiles_silver, df_posts_silver, df_reels_silver, run_id
        )
        aggregator.write(df_gold, settings.GOLD_ENGAGEMENT)
    except Exception as e:
        raise RuntimeError(f"[GOLD] Falha na agregação de métricas: {e}") from e

    return run_id


if __name__ == "__main__":
    load_dotenv()
    import pandas as pd

    df_gov = pd.read_excel(settings.GOVERNADORES_FILE)
    df_gov.columns = df_gov.columns.str.strip()
    token = os.getenv("APIFY_API_TOKEN")
    links = list(df_gov[settings.LINK_COLUMN].str.strip().unique())

    run_id = run_medallion_pipeline(
        apify_api_token=token,
        links=links,
        results_limit=settings.RESULTS_LIMIT,
    )
    print(f"✅ Pipeline Medallion finalizado com run_id: {run_id}")
