import pandas as pd
import streamlit as st
from deltalake.writer import write_deltalake

from config import settings
from dashboard.core import data


def _clear_caches():
    st.cache_resource.clear()
    st.cache_data.clear()


def _point_settings_at(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "GOLD_DIR", tmp_path / "gold")
    monkeypatch.setattr(settings, "SILVER_DIR", tmp_path / "silver")
    _clear_caches()


def test_load_engagement_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    path = settings.GOLD_DIR / "governor_engagement"
    df = pd.DataFrame(
        {
            "id": ["1"],
            "username": ["g"],
            "TOTAL ENGAJAMENTO": [10],
            "% ENGAJAMENTO": [0.1],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    write_deltalake(str(path), df, mode="overwrite")

    out = data.load_engagement()

    assert "% ENGAJAMENTO" in out.columns
    _clear_caches()


def test_load_engagement_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = data.load_engagement()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_engagement_history_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    path = settings.GOLD_DIR / "governor_engagement_history"
    df_r1 = pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "TOTAL ENGAJAMENTO": [10],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    df_r2 = pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "TOTAL ENGAJAMENTO": [20],
            "_run_id": ["r2"],
            "_generated_at": pd.to_datetime(["2026-05-02"], utc=True),
        }
    )
    write_deltalake(str(path), df_r1, mode="overwrite")
    write_deltalake(str(path), df_r2, mode="append")

    out = data.load_engagement_history()

    assert len(out) == 2
    assert set(out["_run_id"]) == {"r1", "r2"}
    _clear_caches()


def test_load_engagement_history_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = data.load_engagement_history()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_sentiment_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    path = settings.GOLD_DIR / "governor_sentiment"
    df = pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "fonte": ["comentario"],
            "sentiment_label": ["positive"],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    write_deltalake(str(path), df, mode="overwrite")

    out = data.load_sentiment()

    assert "sentiment_label" in out.columns
    _clear_caches()


def test_load_sentiment_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = data.load_sentiment()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_sentiment_history_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    path = settings.GOLD_DIR / "governor_sentiment_history"
    df_r1 = pd.DataFrame(
        {
            "id_comment": ["c1"],
            "sentiment_label": ["positive"],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    df_r2 = pd.DataFrame(
        {
            "id_comment": ["c2"],
            "sentiment_label": ["negative"],
            "_run_id": ["r2"],
            "_generated_at": pd.to_datetime(["2026-05-08"], utc=True),
        }
    )
    write_deltalake(str(path), df_r1, mode="overwrite")
    write_deltalake(str(path), df_r2, mode="append")

    out = data.load_sentiment_history()

    assert len(out) == 2
    assert set(out["_run_id"]) == {"r1", "r2"}
    _clear_caches()


def test_load_sentiment_history_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = data.load_sentiment_history()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_clusters_content_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    path = settings.GOLD_DIR / "governor_clusters_reels"
    df = pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "content_type": ["reel"],
            "videoPlayCount": [1000],
            "cluster_label": [0],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    write_deltalake(str(path), df, mode="overwrite")

    out = data.load_clusters_content()

    assert "content_type" in out.columns
    _clear_caches()


def test_load_clusters_content_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = data.load_clusters_content()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_posts_content_returns_delta_table(tmp_path, monkeypatch):
    # ADR 0024: load_posts_content() espelha load_reels_content(), lendo
    # `posts_clean` (Silver) em vez de `reels_clean`.
    _point_settings_at(monkeypatch, tmp_path)
    path = settings.SILVER_DIR / "posts_clean"
    df = pd.DataFrame(
        {
            "id": ["p1"],
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "likesCount": [10],
            "commentsCount": [2],
            "data_hora": pd.to_datetime(["2026-05-01"]),
            "_run_id": ["r1"],
        }
    )
    write_deltalake(str(path), df, mode="overwrite")

    out = data.load_posts_content()

    assert "data_hora" in out.columns
    _clear_caches()


def test_load_posts_content_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = data.load_posts_content()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_clusters_profile_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    path = settings.GOLD_DIR / "governor_profile_clusters_engagement"
    df = pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "cluster_perfil_engajamento": [0],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    write_deltalake(str(path), df, mode="overwrite")

    out = data.load_clusters_profile()

    assert "cluster_perfil_engajamento" in out.columns
    _clear_caches()


def test_load_clusters_profile_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = data.load_clusters_profile()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_discourse_topics_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    path = settings.GOLD_DIR / "governor_discourse_topics"
    df = pd.DataFrame(
        {
            "id_reel": ["r1"],
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "fonte": ["legenda"],
            "Topic": [0],
            "Name": ["0_saude"],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    write_deltalake(str(path), df, mode="overwrite")

    out = data.load_discourse_topics()

    assert "Name" in out.columns
    _clear_caches()


def test_load_discourse_topics_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = data.load_discourse_topics()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_topic_priority_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    path = settings.GOLD_DIR / "topic_priority_score"
    df = pd.DataFrame(
        {
            "Topic": [0],
            "Name": ["0_saude"],
            "score": [0.5],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    write_deltalake(str(path), df, mode="overwrite")

    out = data.load_topic_priority()

    assert "score" in out.columns
    _clear_caches()


def test_load_topic_priority_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = data.load_topic_priority()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_nsm_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    path = settings.GOLD_DIR / "governor_nsm"
    df = pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "username": ["governador_a"],
            "nsm": [0.42],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    write_deltalake(str(path), df, mode="overwrite")

    out = data.load_nsm()

    assert "nsm" in out.columns
    _clear_caches()


def test_load_nsm_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = data.load_nsm()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_growth_metrics_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    path = settings.GOLD_DIR / "governor_growth_metrics"
    df = pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "cmgr": [0.05],
            "cmgr_confiavel": [False],
            "nota": ["histórico curto — ilustrativo"],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    write_deltalake(str(path), df, mode="overwrite")

    out = data.load_growth_metrics()

    assert "cmgr" in out.columns
    _clear_caches()


def test_load_growth_metrics_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = data.load_growth_metrics()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_governors_metadata_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    path = settings.SILVER_DIR / "governors_metadata"
    df = pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "nome": ["Governador A"],
            "uf": ["SP"],
            "regiao": ["Sudeste"],
            "partido": ["PARTIDO"],
        }
    )
    write_deltalake(str(path), df, mode="overwrite")

    out = data.load_governors_metadata()

    assert "uf" in out.columns
    _clear_caches()


def test_load_governors_metadata_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = data.load_governors_metadata()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_comments_only_keeps_only_comentario_source():
    df = pd.DataFrame(
        {
            "inputUrl": ["a", "b", "c"],
            "fonte": ["comentario", "legenda", "transcricao"],
            "sentiment_label": ["positive", "neutral", "negative"],
        }
    )

    out = data.comments_only(df)

    assert set(out["fonte"]) == {"comentario"}
    assert len(out) == 1
