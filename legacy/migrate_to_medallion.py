"""
Legacy migration script to move existing JSON/Excel data into Medallion Delta tables.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from config import settings
from src.data_extract.bronze_writer import BronzeWriter
from src.data_extract.readers import JsonDataReader
from src.features.gold.engagement_aggregator import EngagementAggregator
from src.features.gold.model_enricher import ModelEnricher
from src.features.silver.comment_cleaner import CommentCleaner
from src.features.silver.post_cleaner import PostCleaner
from src.features.silver.profile_cleaner import ProfileCleaner

MIGRATION_RUN_ID = "migration_from_xlsx_v1"


def migrate():
    print("🔄 Iniciando migração para arquitetura Medallion...")

    sources_exist = {
        "profiles.json": settings.PROFILES_JSON.exists(),
        "posts.json": settings.POSTS_JSON.exists(),
        "reels.json": settings.REELS_JSON.exists(),
        "all.xlsx": settings.ALL_XLSX.exists(),
    }
    missing = [k for k, v in sources_exist.items() if not v]
    if missing:
        print(f"⚠️  Arquivos não encontrados: {missing}")
        print("   Execute o pipeline legado primeiro: uv run python pipeline_legacy.py")
        return

    print("\n🥉 Migrando para Bronze...")
    reader = JsonDataReader()
    bronze = BronzeWriter(
        bronze_profiles_path=settings.BRONZE_PROFILES,
        bronze_posts_path=settings.BRONZE_POSTS,
        bronze_reels_path=settings.BRONZE_REELS,
    )

    profiles_data = reader.read(settings.PROFILES_JSON).to_dict("records")
    posts_data = reader.read(settings.POSTS_JSON).to_dict("records")
    reels_data = reader.read(settings.REELS_JSON).to_dict("records")

    bronze.write_profiles(profiles_data, run_id=MIGRATION_RUN_ID)
    bronze.write_posts(posts_data, run_id=MIGRATION_RUN_ID)
    bronze.write_reels(reels_data, run_id=MIGRATION_RUN_ID)
    print(
        f"   ✅ Bronze: {len(profiles_data)} perfis, {len(posts_data)} posts, {len(reels_data)} reels"
    )

    print("\n🥈 Migrando para Silver...")
    profile_cleaner = ProfileCleaner()
    post_cleaner = PostCleaner()
    comment_cleaner = CommentCleaner()

    df_profiles_raw = bronze.get_latest_profiles()
    df_posts_raw = bronze.get_latest_posts()
    df_reels_raw = bronze.get_latest_reels()

    df_profiles_silver = profile_cleaner.clean(df_profiles_raw, MIGRATION_RUN_ID)
    df_posts_silver = post_cleaner.clean_posts(df_posts_raw)
    df_reels_silver = post_cleaner.clean_reels(df_reels_raw)
    df_comments_silver = comment_cleaner.clean(df_reels_raw)

    profile_cleaner.write(df_profiles_silver, settings.SILVER_PROFILES)
    post_cleaner.write_posts(df_posts_silver, settings.SILVER_POSTS)
    post_cleaner.write_reels(df_reels_silver, settings.SILVER_REELS)
    comment_cleaner.write(df_comments_silver, settings.SILVER_COMMENTS)
    print(
        f"   ✅ Silver: {len(df_profiles_silver)} perfis, {len(df_comments_silver)} comentários"
    )

    print("\n🥇 Migrando para Gold...")
    aggregator = EngagementAggregator()
    df_gold = aggregator.aggregate(
        df_profiles_silver, df_posts_silver, df_reels_silver, MIGRATION_RUN_ID
    )
    aggregator.write(df_gold, settings.GOLD_ENGAGEMENT)
    print(f"   ✅ Gold engajamento: {len(df_gold)} governadores")

    print("\n🥇 Tentando migrar dados de modelo do all.xlsx...")
    try:
        df_comments_modeled = pd.read_excel(
            settings.ALL_XLSX, sheet_name="reels_latestComments"
        )
        if "sentiment_label" in df_comments_modeled.columns:
            enricher = ModelEnricher()
            enricher.write_sentiment(
                df_comments_modeled, settings.GOLD_SENTIMENT, MIGRATION_RUN_ID
            )
            print(
                f"   ✅ Gold sentimentos: {len(df_comments_modeled)} comentários migrados"
            )
        else:
            print(
                "   ℹ️  Dados de sentimento não encontrados no all.xlsx — execute notebook 03."
            )
    except Exception as e:
        print(f"   ℹ️  Não foi possível migrar dados de modelo: {e}")

    print("\n✅ Migração concluída!")
    print(f"   Run ID de migração: {MIGRATION_RUN_ID}")


if __name__ == "__main__":
    migrate()
