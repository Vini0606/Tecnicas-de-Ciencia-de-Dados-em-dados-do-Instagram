"""
Derivacao deterministica Silver/Gold a partir da Bronze (ADR 0039, issue #253).

Etapa unica, reutilizada por `coletar()` (Coleta local) e pela Lambda de
reconstrucao (S3): le a Bronze e grava Silver e Gold, sem rede, sem Apify e
sem modelagem pesada. O `destino` pode ser uma pasta local ou uma URI
(`s3://bucket/prefixo`); a escrita Delta usa as credenciais do ambiente.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from src.data_extract.bronze_writer import BronzeWriter
from src.features.gold.engagement_aggregator import EngagementAggregator
from src.features.gold.ugc_mentions_aggregator import GovernorUGCAggregator
from src.features.silver.comment_cleaner import CommentCleaner
from src.features.silver.post_cleaner import PostCleaner
from src.features.silver.profile_cleaner import ProfileCleaner
from src.features.silver.ugc_mention_cleaner import UGCMentionCleaner

logger = logging.getLogger(__name__)


def _juntar(base: Path | str, *partes: str) -> Path | str:
    if "://" in str(base):
        return "/".join([str(base).rstrip("/"), *partes])
    return Path(base).joinpath(*partes)


def caminhos_do_destino(destino: Path | str) -> dict[str, Path | str]:
    """Layout de `config.settings` (`bronze/instagram_*`, `silver/*_clean`,
    `gold/governor_*`) sob `destino`, local ou URI."""
    return {
        "bronze_profiles": _juntar(destino, "bronze", "instagram_profiles"),
        "bronze_posts": _juntar(destino, "bronze", "instagram_posts"),
        "bronze_reels": _juntar(destino, "bronze", "instagram_reels"),
        "bronze_ugc": _juntar(destino, "bronze", "ugc_mentions"),
        "silver_profiles": _juntar(destino, "silver", "profiles_clean"),
        "silver_posts": _juntar(destino, "silver", "posts_clean"),
        "silver_reels": _juntar(destino, "silver", "reels_clean"),
        "silver_comments": _juntar(destino, "silver", "comments_clean"),
        "silver_post_comments": _juntar(destino, "silver", "post_comments_clean"),
        "silver_governors": _juntar(destino, "silver", "governors_metadata"),
        "silver_ugc": _juntar(destino, "silver", "ugc_mentions"),
        "gold_engagement": _juntar(destino, "gold", "governor_engagement"),
        "gold_engagement_history": _juntar(destino, "gold", "governor_engagement_history"),
        "gold_ugc": _juntar(destino, "gold", "governor_ugc_mentions"),
    }


def derivar_silver_gold(
    bronze: BronzeWriter,
    p: dict[str, Path | str],
    governor_usernames: list[str],
    run_id: str,
    *,
    modo_historico: str = "append",
    modelar: Callable[[dict[str, pd.DataFrame]], None] | None = None,
) -> pd.DataFrame:
    """Le a Bronze (`bronze`) e grava Silver/Gold nos caminhos `p`
    (`caminhos_do_destino`). A Silver de governadores nao entra aqui: vem da
    planilha, nao da Bronze. Devolve o Gold de engajamento.

    `modo_historico` e o modo de escrita do historico de engajamento
    (`append` na Coleta; `overwrite` ao reconstruir, para ser idempotente)."""
    df_profiles = bronze.get_latest_profiles()
    df_posts = bronze.get_latest_posts()
    df_reels = bronze.get_latest_reels()

    profile_cleaner, post_cleaner = ProfileCleaner(), PostCleaner()
    comment_cleaner, post_comment_cleaner = CommentCleaner(), CommentCleaner(origem="post")
    silver_profiles = profile_cleaner.clean(df_profiles, governor_usernames)
    silver_posts = post_cleaner.clean_posts(df_posts, governor_usernames)
    silver_reels = post_cleaner.clean_reels(df_reels, governor_usernames)
    silver_comments = comment_cleaner.clean(df_reels, governor_usernames)
    silver_post_comments = post_comment_cleaner.clean(df_posts, governor_usernames)

    profile_cleaner.write(silver_profiles, p["silver_profiles"])
    post_cleaner.write_posts(silver_posts, p["silver_posts"])
    post_cleaner.write_reels(silver_reels, p["silver_reels"])
    comment_cleaner.write(silver_comments, p["silver_comments"])
    if not silver_post_comments.empty:
        post_comment_cleaner.write(silver_post_comments, p["silver_post_comments"])

    silver_ugc = _silver_ugc(bronze, governor_usernames, p["silver_ugc"])

    aggregator = EngagementAggregator()
    gold = aggregator.aggregate(silver_profiles, silver_posts, silver_reels, run_id)
    aggregator.write(gold, p["gold_engagement"])
    aggregator.write(gold, p["gold_engagement_history"], mode=modo_historico)
    if silver_ugc is not None:
        ugc_aggregator = GovernorUGCAggregator()
        ugc_aggregator.write(ugc_aggregator.enrich(silver_ugc, run_id=run_id), p["gold_ugc"])

    if modelar is not None:
        modelar(
            {
                "reels": silver_reels,
                "comments": silver_comments,
                "posts": silver_posts,
                "post_comments": silver_post_comments,
                "engagement": gold,
            }
        )
    return gold


def _silver_ugc(
    bronze: BronzeWriter, governor_usernames: list[str], caminho: Path | str
) -> pd.DataFrame | None:
    """UGC nunca derruba a Coleta (issue #211): sem Bronze de UGC ou com falha
    na limpeza, a etapa e pulada com aviso."""
    try:
        df_bronze_ugc = bronze.get_latest_ugc_mentions()
    except FileNotFoundError:
        logger.warning("[SILVER] Bronze de UGC inexistente -- etapa de UGC pulada.")
        return None
    try:
        cleaner = UGCMentionCleaner()
        df = cleaner.clean(df_bronze_ugc, governor_usernames)
        if df.empty:
            logger.warning("[SILVER] Silver de UGC vazia -- etapa de UGC pulada.")
            return None
        cleaner.write(df, caminho)
        return df
    except Exception:
        logger.exception("[SILVER] Falha na limpeza de UGC -- etapa de UGC pulada.")
        return None
