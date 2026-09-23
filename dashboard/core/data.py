"""Camada de acesso a dado do novo dashboard (ADR 0021 / issue #110).

Um wrapper `@st.cache_data(ttl=600)` por tabela Gold, delegando para os
métodos JÁ NOMEADOS de `DeltaRepository` -- nenhum método genérico
`.read(tabela)` é introduzido aqui (esse método não existe no repositório
real; ver issue #110, Implementation Decisions). Mesmo padrão degradado de
`src/dashboard/loaders.py` (o pacote antigo, ainda em uso por `app.py`/
`pages/*.py` até a Tela 1 substituí-los): `DataFrame` vazio, nunca exceção,
quando a tabela Gold ainda não foi gerada.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config import settings
from src.repositories.delta_repository import DeltaRepository

_TTL_SECONDS = 600


@st.cache_resource
def get_repository() -> DeltaRepository:
    return DeltaRepository(gold_dir=settings.GOLD_DIR, silver_dir=settings.SILVER_DIR)


@st.cache_data(ttl=_TTL_SECONDS)
def load_engagement() -> pd.DataFrame:
    """`governor_engagement` -- 1 linha por perfil (snapshot)."""
    try:
        return get_repository().load_profiles()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data(ttl=_TTL_SECONDS)
def load_engagement_history() -> pd.DataFrame:
    """`governor_engagement_history` -- 1 linha por perfil por execução."""
    try:
        return get_repository().load_engagement_history()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data(ttl=_TTL_SECONDS)
def load_sentiment() -> pd.DataFrame:
    """`governor_sentiment` cru (todas as `fonte`) -- use `comments_only()`
    para reação do público (comentários), não discurso da assessoria
    (legenda/transcrição)."""
    try:
        return get_repository().load_comments()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data(ttl=_TTL_SECONDS)
def load_sentiment_history() -> pd.DataFrame:
    """`governor_sentiment_history` -- idem, modo append por execução."""
    try:
        return get_repository().load_sentiment_history()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data(ttl=_TTL_SECONDS)
def load_clusters_content() -> pd.DataFrame:
    """`governor_clusters_reels` -- 1 linha por reel (`id_reel`/
    `ownerUsername`/`cluster_*`/`content_type`). NÃO tem `videoPlayCount`
    nem `inputUrl` (`GOLD_CLUSTERS_SCHEMA`) -- corrigido pela issue #114
    (Tela 6/Funil), que precisou desse dado e descobriu a lacuna: quem
    precisar de `videoPlayCount` por reel deve cruzar o resultado desta
    função com `load_reels_content()` por `id`/`id_reel` (mesmo join já
    usado em `dashboard/screens/{resumo,produzir,funil}.py`).

    Desde a issue #152, `governor_clusters` deixou de ser uma tabela única
    discriminada por `content_type` (que duplicava posts sobrepostos entre
    `posts_clean`/`reels_clean`) e virou duas tabelas por formato. Esta
    função só expõe a de reels -- os três consumidores atuais
    (`dashboard/screens/{resumo,produzir,funil}.py`) já filtravam
    `content_type == "reel"` sobre o resultado; esse filtro continua
    correto (agora redundante, mas inofensivo) contra a tabela só-de-reel."""
    try:
        return get_repository().load_clusters_reels()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data(ttl=_TTL_SECONDS)
def load_reels_content() -> pd.DataFrame:
    """`reels_clean` (Silver) -- 1 linha por reel, incluindo `Total de
    Engajamento` (likes+comentários por reel) e `inputUrl`. Adicionado na
    issue #111 (Tela 1): `governor_clusters` (`load_clusters_content()`) NÃO
    grava nenhuma métrica de engajamento por post nem `inputUrl`
    (`GOLD_CLUSTERS_SCHEMA` só tem `id_reel`/`ownerUsername`/`cluster_*`/
    `content_type` -- conferido contra `src/features/gold/model_enricher.py`
    `write_clusters` antes de escrever este loader), então o destaque
    "melhor post da semana" precisa cruzar `governor_clusters` com esta
    tabela por `id`/`id_reel` para saber QUAL reel teve mais engajamento --
    mesmo join já usado em `src/dashboard/filters.py::build_cluster_membership`
    e em `pages/02_insights.py`/`pages/05_funil.py`."""
    try:
        return get_repository().load_reels()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data(ttl=_TTL_SECONDS)
def load_posts_content() -> pd.DataFrame:
    """`posts_clean` (Silver) -- 1 linha por post de feed (foto/carrossel),
    incluindo `data_hora` (publicação real), `likesCount`, `commentsCount` e
    `inputUrl`. Espelha `load_reels_content()` (ADR 0024) -- sem
    `videoPlayCount`/`Total de Engajamento` (campos exclusivos de reel, ver
    `SILVER_POSTS_SCHEMA`/`SILVER_REELS_SCHEMA` em `src/schemas_delta.py`)."""
    try:
        return get_repository().load_posts()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data(ttl=_TTL_SECONDS)
def load_clusters_profile() -> pd.DataFrame:
    """`governor_profile_clusters_engagement` -- 1 linha por governador."""
    try:
        return get_repository().load_profile_clusters_engagement()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data(ttl=_TTL_SECONDS)
def load_discourse_topics() -> pd.DataFrame:
    """`governor_discourse_topics` -- 1 linha por legenda/transcrição."""
    try:
        return get_repository().load_discourse_topics()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data(ttl=_TTL_SECONDS)
def load_topic_priority() -> pd.DataFrame:
    """`topic_priority_score` -- 1 linha por tópico de comentário, ranking
    global (não por governador)."""
    try:
        return get_repository().load_topic_priority_score()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data(ttl=_TTL_SECONDS)
def load_nsm() -> pd.DataFrame:
    """`governor_nsm` -- 1 linha por perfil."""
    try:
        return get_repository().load_nsm()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data(ttl=_TTL_SECONDS)
def load_nsm_history() -> pd.DataFrame:
    """`governor_nsm_history` -- 1 linha por perfil por execução (ADR 0025 /
    issue #153), espelha `load_engagement_history()`. NOTA: em 2026-09 a
    pipeline ainda não escreve esta tabela (`NsmScorer.write` grava
    `governor_nsm` em modo `overwrite`, sem variante de histórico -- ver
    `src/repositories/delta_repository.py::load_nsm_history`); até essa
    mudança de pipeline acontecer (fora do escopo da issue #153), esta
    função sempre degrada para `DataFrame` vazio, e o KPI de NSM no Resumo
    fica sem seta de variação -- comportamento esperado, não um bug."""
    try:
        return get_repository().load_nsm_history()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data(ttl=_TTL_SECONDS)
def load_growth_metrics() -> pd.DataFrame:
    """`governor_growth_metrics` -- 1 linha por perfil (`cmgr_confiavel`/
    `retencao_confiavel` sempre precisam ser checados antes de exibir)."""
    try:
        return get_repository().load_growth_metrics()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data(ttl=_TTL_SECONDS)
def load_governors_metadata() -> pd.DataFrame:
    """`governors_metadata` -- 1 linha por governador (nome/UF/partido)."""
    try:
        return get_repository().load_governors_metadata()
    except FileNotFoundError:
        return pd.DataFrame()


def comments_only(df: pd.DataFrame) -> pd.DataFrame:
    """Reação do público = só comentários (`fonte == 'comentario'`); o resto
    de `governor_sentiment` (`legenda`, `transcricao`) é discurso da própria
    assessoria, não reação de quem consome. Retorna cópia -- quem chama pode
    mutar o resultado sem afetar o DataFrame original nem o cache."""
    if df.empty or "fonte" not in df.columns:
        return df.copy()
    return df[df["fonte"] == "comentario"].copy()
