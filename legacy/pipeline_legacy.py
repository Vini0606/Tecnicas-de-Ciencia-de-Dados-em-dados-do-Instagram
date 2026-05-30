"""Legacy pipeline that generates the older Excel-based dataset (`all.xlsx`)."""

import os

from apify_client import ApifyClient
from dotenv import load_dotenv

from config import settings
from src.data_extract.readers import JsonDataReader
from src.data_extract.scraper import InstagramScraper, ScraperConfig
from src.features.comments import CommentsTransformer
from src.features.engagement import EngagementFeatureBuilder
from src.repositories.excel_repository import ExcelDataRepository


def run_pipeline(
    apify_api_token: str,
    links: list[str],
    results_limit: int = 30,
    force_extract: bool = False,
) -> None:
    """
    Orquestra o pipeline ETL completo.

    Args:
        apify_api_token: Token da API Apify.
        links: Lista de URLs dos perfis do Instagram.
        results_limit: Limite de posts/reels por perfil.
        force_extract: Se True, re-extrai mesmo se os arquivos já existirem.
    """
    reader = JsonDataReader()

    # --- EXTRAÇÃO ---
    files_exist = all(
        [
            settings.PROFILES_JSON.exists(),
            settings.POSTS_JSON.exists(),
            settings.REELS_JSON.exists(),
        ]
    )

    if not files_exist or force_extract:
        print("🔍 [1/3] EXTRAÇÃO: Buscando dados na API Apify...")
        try:
            client = ApifyClient(apify_api_token)
            config = ScraperConfig(results_limit=results_limit)
            scraper = InstagramScraper(client=client, config=config)

            profiles_data = scraper.scrape_profiles(links)
            posts_data = scraper.scrape_posts(links)
            reels_data = scraper.scrape_reels(links)

            reader.save(profiles_data, settings.PROFILES_JSON)
            reader.save(posts_data, settings.POSTS_JSON)
            reader.save(reels_data, settings.REELS_JSON)
        except Exception as e:
            raise RuntimeError("[EXTRAÇÃO] Falha ao buscar dados na API Apify") from e
    else:
        print("📁 [1/3] EXTRAÇÃO: Arquivos já existem. Pulando...")

    # --- TRANSFORMAÇÃO ---
    print("🔧 [2/3] TRANSFORMAÇÃO: Processando dados...")

    try:
        df_profiles = reader.read(settings.PROFILES_JSON)
        df_posts = reader.read(settings.POSTS_JSON)
        df_reels = reader.read(settings.REELS_JSON)
    except Exception as e:
        raise RuntimeError("[LEITURA] Falha ao ler arquivos JSON do disco") from e

    try:
        engagement_builder = EngagementFeatureBuilder()
        df_profiles_enriched, df_combined = engagement_builder.build(
            df_profiles, df_posts, df_reels
        )
    except Exception as e:
        raise RuntimeError(
            "[TRANSFORMAÇÃO] Falha ao calcular features de engajamento"
        ) from e

    try:
        comments_transformer = CommentsTransformer()
        df_comments = comments_transformer.transform(df_reels)
    except Exception as e:
        raise RuntimeError("[TRANSFORMAÇÃO] Falha ao processar comentários") from e

    # --- CARGA ---
    print("💾 [3/3] CARGA: Salvando dados processados...")

    try:
        repo = ExcelDataRepository(settings.ALL_XLSX)
        repo.save(
            {
                "profiles": df_profiles_enriched,
                "posts": df_posts,
                "reels": df_reels,
                "reels_latestComments": df_comments,
                "reels_posts": df_combined,
            }
        )
    except Exception as e:
        raise RuntimeError("[CARGA] Falha ao salvar o arquivo Excel processado") from e

    print(f"✅ Pipeline finalizado! Arquivo salvo em: {settings.ALL_XLSX}")


if __name__ == "__main__":
    load_dotenv()
    import pandas as pd

    df_gov = pd.read_excel(settings.GOVERNADORES_FILE)
    df_gov.columns = df_gov.columns.str.strip()
    token = os.getenv("APIFY_API_TOKEN")
    links = list(df_gov["Link"].str.strip().unique())

    run_pipeline(apify_api_token=token, links=links, results_limit=30)
