import logging
import os
from typing import Callable

import pandas as pd
from apify_client import ApifyClient
from dotenv import load_dotenv

from config import settings
from scripts.apify_backfill_shared import estimate_cost_usd_for_results_limit
from src.data_extract.bronze_writer import BronzeWriter
from src.data_extract.ingestion import extract_and_land
from src.data_extract.scraper import InstagramScraper, ScraperConfig
from src.features.gold.engagement_aggregator import EngagementAggregator
from src.features.silver.comment_cleaner import CommentCleaner
from src.features.silver.governors_metadata_cleaner import GovernorsMetadataCleaner
from src.features.silver.post_cleaner import PostCleaner
from src.features.silver.profile_cleaner import ProfileCleaner
from src.logging_setup import attach_run_log_handler, configure_console_logging
from src.modeling.config import ModelingConfig
from src.modeling.orchestration import run_deterministic_modeling
from src.run_id import build_run_id

logger = logging.getLogger(__name__)


def _bronze_has_data(bronze: BronzeWriter) -> bool:
    try:
        df = bronze.get_latest_profiles()
        return not df.empty
    except Exception:
        return False


def run_medallion_pipeline(
    apify_api_token: str,
    links: list[str],
    results_limit: int = 30,
    run_id: str | None = None,
    force_extract: bool = False,
    run_modeling: bool = False,
    confirm_extraction: Callable[[float], bool] | None = None,
) -> str:
    run_id = build_run_id(run_id)

    bronze = BronzeWriter(
        bronze_profiles_path=settings.BRONZE_PROFILES,
        bronze_posts_path=settings.BRONZE_POSTS,
        bronze_reels_path=settings.BRONZE_REELS,
    )

    try:
        if not force_extract and _bronze_has_data(bronze):
            df_profiles = bronze.get_latest_profiles()
            df_posts = bronze.get_latest_posts()
            df_reels = bronze.get_latest_reels()
        else:
            if not apify_api_token:
                raise ValueError(
                    "APIFY_API_TOKEN não fornecido e não há dados brutos locais."
                )
            if confirm_extraction is not None:
                estimated_cost = estimate_cost_usd_for_results_limit(
                    results_limit, len(links)
                )
                if not confirm_extraction(estimated_cost):
                    raise SystemExit(1)
            logger.info("[1/3] BRONZE: Extraindo dados brutos...")
            scraper = InstagramScraper(
                client=ApifyClient(apify_api_token),
                config=ScraperConfig(results_limit=results_limit),
            )
            extract_and_land(scraper, bronze, settings.LANDING_DIR, links, run_id=run_id)

            df_profiles = bronze.get_latest_profiles()
            df_posts = bronze.get_latest_posts()
            df_reels = bronze.get_latest_reels()
    except Exception as e:
        raise RuntimeError(f"[BRONZE] Falha na ingestão de dados brutos: {e}") from e

    try:
        logger.info("[2/3] SILVER: Limpando e conformando dados...")
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

        # Dimensão de metadados dos governadores (nome/UF/partido), ingerida
        # de `governadores.xlsx` -- não vem do scraper, então não passa por
        # Bronze (ver decisão de design: planilha mantida manualmente, já
        # relativamente limpa de origem, não precisa do estágio de proteção
        # contra reprocessamento que a Bronze existe para dar aos dados do Apify).
        governors_cleaner = GovernorsMetadataCleaner()
        df_governors_raw = pd.read_excel(settings.GOVERNADORES_FILE)
        df_governors_silver = governors_cleaner.clean(df_governors_raw, run_id)
        governors_cleaner.write(df_governors_silver, settings.SILVER_GOVERNORS_METADATA)
    except Exception as e:
        raise RuntimeError(
            f"[SILVER] Falha na limpeza e conformação dos dados: {e}"
        ) from e

    try:
        logger.info("[3/3] GOLD: Agregando métricas de engajamento...")
        aggregator = EngagementAggregator()
        df_gold = aggregator.aggregate(
            df_profiles_silver, df_posts_silver, df_reels_silver, run_id
        )
        aggregator.write(df_gold, settings.GOLD_ENGAGEMENT)
    except Exception as e:
        raise RuntimeError(f"[GOLD] Falha na agregação de métricas: {e}") from e

    if run_modeling:
        # Só o estágio determinístico. O refinamento de tópicos via Gemini
        # (src.modeling.orchestration.refine_topics_with_gemini) fica de
        # fora de propósito — é uma etapa manual e de revisão humana, não
        # deve rodar sozinha a cada execução do pipeline (ver ADR 0001).
        try:
            logger.info(
                "[MODELAGEM] Rodando estágio determinístico "
                "(PCA -> clustering -> sentimento -> tópicos)..."
            )
            result = run_deterministic_modeling(
                df_reels_silver, df_comments_silver, ModelingConfig()
            )
            logger.info(f"[MODELAGEM] Concluída com run_id: {result.run_id}")
        except Exception as e:
            raise RuntimeError(f"[MODELAGEM] Falha no estágio determinístico: {e}") from e

    return run_id


if __name__ == "__main__":
    import argparse

    load_dotenv()

    parser = argparse.ArgumentParser(description="Roda o pipeline Medallion (Bronze/Silver/Gold).")
    parser.add_argument(
        "--run-modeling",
        action="store_true",
        help=(
            "Roda tambem o estagio deterministico de modelagem ao final do "
            "Gold (pesado: ~14 min so o embedding do BERTopic). O "
            "refinamento via Gemini nunca roda daqui -- ver scripts/refine_topics.py."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help=(
            "Confirma uma extracao real na Apify (custo real), caso nao haja "
            "Bronze/raw local em cache. Obrigatorio so quando o cache esta "
            "vazio -- se a Bronze ja tem dado, o pipeline reusa e nao pede "
            "confirmacao."
        ),
    )
    args = parser.parse_args()

    configure_console_logging()
    # run_id gerado aqui (não deixado para run_medallion_pipeline) porque o
    # handler de arquivo por run_id (ADR 0015) precisa ser anexado antes de
    # qualquer trabalho começar -- inclusive antes da eventual extração real.
    run_id = build_run_id()
    attach_run_log_handler(run_id, settings.LOGS_DIR)

    df_gov = pd.read_excel(settings.GOVERNADORES_FILE)
    df_gov.columns = df_gov.columns.str.strip()
    token = os.getenv("APIFY_API_TOKEN")
    links = list(df_gov[settings.LINK_COLUMN].str.strip().unique())

    def _confirm_extraction(estimated_cost: float) -> bool:
        if args.yes:
            return True
        logger.info(
            f"[ABORTADO] Nao ha Bronze/raw local em cache -- rodar agora "
            f"dispararia uma extracao real na Apify (~${estimated_cost} "
            f"estimado no pior caso para {len(links)} governadores, "
            f"resultsLimit={settings.RESULTS_LIMIT}, sem janela de data). "
            "Rode de novo com --yes para confirmar."
        )
        return False

    run_id = run_medallion_pipeline(
        apify_api_token=token,
        links=links,
        results_limit=settings.RESULTS_LIMIT,
        run_id=run_id,
        run_modeling=args.run_modeling,
        confirm_extraction=_confirm_extraction,
    )
    # Sem emoji: o console padrão do Windows usa cp1252 e levanta
    # UnicodeEncodeError ao imprimi-los.
    logger.info(f"[OK] Pipeline Medallion finalizado com run_id: {run_id}")
