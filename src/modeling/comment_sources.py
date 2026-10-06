"""
Combinação das duas origens de comentário (issue #212) antes da modelagem:
reels (`comments_clean`, `id_reel`) e posts de feed (`post_comments_clean`,
`id_post`).
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def combine_comment_sources(
    df_reel_comments: pd.DataFrame, df_post_comments: pd.DataFrame | None
) -> pd.DataFrame:
    """Une comentários de reels e de posts num único DataFrame com
    `origem_comentario` ("reel"/"post"), renomeando `id_post` para `id_reel`
    (que passa a significar "id da publicação comentada").

    Um reel também é capturado pelo scraper de posts (issue #152), então o
    mesmo comentário pode vir das duas origens: deduplica por `id_comment`
    mantendo a linha de reel, que preserva os joins com
    `governor_clusters_reels`/`reels_clean`."""
    df_reels = df_reel_comments.assign(origem_comentario="reel")
    if df_post_comments is None or df_post_comments.empty:
        df_posts = df_reels.iloc[0:0]
    else:
        df_posts = df_post_comments.rename(columns={"id_post": "id_reel"}).assign(
            origem_comentario="post"
        )

    df = pd.concat([df_reels, df_posts], ignore_index=True)
    if "id_comment" in df.columns:
        # Reels primeiro no concat: `keep="first"` preserva a origem reel.
        tem_id = df["id_comment"].notna()
        df = pd.concat(
            [df[tem_id].drop_duplicates(subset=["id_comment"], keep="first"), df[~tem_id]],
            ignore_index=True,
        )
    duplicados = len(df_reels) + len(df_posts) - len(df)
    logger.info(
        "[COMENTARIOS] Origens combinadas: reels=%d posts=%d duplicados=%d total=%d",
        len(df_reels),
        len(df_posts),
        duplicados,
        len(df),
    )
    return df
