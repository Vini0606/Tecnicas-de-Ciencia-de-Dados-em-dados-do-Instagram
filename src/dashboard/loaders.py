from __future__ import annotations

import pandas as pd
import streamlit as st

from config import settings
from src.repositories.base import DataRepository
from src.repositories.delta_repository import DeltaRepository


@st.cache_resource
def get_repository() -> DataRepository:
    return DeltaRepository(gold_dir=settings.GOLD_DIR, silver_dir=settings.SILVER_DIR)


@st.cache_resource
def get_delta_repository() -> DeltaRepository:
    repo = get_repository()
    if not isinstance(repo, DeltaRepository):
        raise TypeError(
            f"load_clusters() exige DeltaRepository (clusters só existem no Gold via Delta); "
            f"get_repository() retornou {type(repo).__name__}."
        )
    return repo


@st.cache_data
def load_profiles() -> pd.DataFrame:
    return get_repository().load_profiles()


@st.cache_data
def load_comments() -> pd.DataFrame:
    return get_repository().load_comments()


@st.cache_data
def load_reels() -> pd.DataFrame:
    return get_repository().load_reels()


@st.cache_data
def load_clusters() -> pd.DataFrame:
    try:
        return get_delta_repository().load_clusters()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data
def load_governors_metadata() -> pd.DataFrame:
    try:
        return get_delta_repository().load_governors_metadata()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data
def load_profile_clusters_engagement() -> pd.DataFrame:
    try:
        return get_delta_repository().load_profile_clusters_engagement()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data(ttl=settings.DASHBOARD_REFRESH_SECONDS)
def load_engagement_history() -> pd.DataFrame:
    # TTL curto (ao contrário dos loaders acima) para o auto-refresh da
    # página de monitoramento reler a Delta de verdade a cada rerun.
    try:
        return get_delta_repository().load_engagement_history()
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_data
def load_sentiment_history() -> pd.DataFrame:
    # Sem TTL (ao contrário de load_engagement_history) -- modelagem não
    # roda por execução de extração (ADR 0011), não precisa de auto-refresh
    # (issue #61).
    try:
        return get_delta_repository().load_sentiment_history()
    except FileNotFoundError:
        return pd.DataFrame()
