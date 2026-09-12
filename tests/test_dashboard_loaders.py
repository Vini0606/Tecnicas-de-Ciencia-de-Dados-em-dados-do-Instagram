import pandas as pd
import streamlit as st
from deltalake.writer import write_deltalake

from config import settings
from src.dashboard import loaders
from src.repositories.delta_repository import DeltaRepository


def _clear_caches():
    st.cache_resource.clear()
    st.cache_data.clear()


def _point_settings_at(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "GOLD_DIR", tmp_path / "gold")
    monkeypatch.setattr(settings, "SILVER_DIR", tmp_path / "silver")
    _clear_caches()


def test_load_profiles_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    engagement_path = settings.GOLD_DIR / "governor_engagement"
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
    write_deltalake(str(engagement_path), df, mode="overwrite")

    out = loaders.load_profiles()

    assert "% ENGAJAMENTO" in out.columns
    _clear_caches()


def test_load_clusters_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = loaders.load_clusters()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_get_delta_repository_resolves_to_delta_repository(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    repo = loaders.get_delta_repository()

    assert isinstance(repo, DeltaRepository)
    _clear_caches()


def test_load_engagement_history_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    history_path = settings.GOLD_DIR / "governor_engagement_history"
    df_r1 = pd.DataFrame(
        {
            "id": ["1"],
            "username": ["g"],
            "TOTAL ENGAJAMENTO": [10],
            "% ENGAJAMENTO": [0.1],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    df_r2 = pd.DataFrame(
        {
            "id": ["1"],
            "username": ["g"],
            "TOTAL ENGAJAMENTO": [20],
            "% ENGAJAMENTO": [0.2],
            "_run_id": ["r2"],
            "_generated_at": pd.to_datetime(["2026-05-02"], utc=True),
        }
    )
    write_deltalake(str(history_path), df_r1, mode="overwrite")
    write_deltalake(str(history_path), df_r2, mode="append")

    out = loaders.load_engagement_history()

    assert len(out) == 2
    assert set(out["_run_id"]) == {"r1", "r2"}
    _clear_caches()


def test_load_engagement_history_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = loaders.load_engagement_history()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_sentiment_history_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    history_path = settings.GOLD_DIR / "governor_sentiment_history"
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
    write_deltalake(str(history_path), df_r1, mode="overwrite")
    write_deltalake(str(history_path), df_r2, mode="append")

    out = loaders.load_sentiment_history()

    assert len(out) == 2
    assert set(out["_run_id"]) == {"r1", "r2"}
    _clear_caches()


def test_load_sentiment_history_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = loaders.load_sentiment_history()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_post_performance_coefficients_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    path = settings.GOLD_DIR / "post_performance_coefficients"
    df = pd.DataFrame(
        {
            "grupo": ["video"],
            "preditor": ["hora_do_dia"],
            "coeficiente": [0.1],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    write_deltalake(str(path), df, mode="overwrite")

    out = loaders.load_post_performance_coefficients()

    assert "coeficiente" in out.columns
    _clear_caches()


def test_load_post_performance_coefficients_returns_empty_dataframe_when_missing(
    tmp_path, monkeypatch
):
    _point_settings_at(monkeypatch, tmp_path)

    out = loaders.load_post_performance_coefficients()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_post_performance_predictions_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    path = settings.GOLD_DIR / "post_performance_predictions"
    df = pd.DataFrame(
        {
            "id": ["p1"],
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "grupo": ["estatico"],
            "residuo": [0.05],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    write_deltalake(str(path), df, mode="overwrite")

    out = loaders.load_post_performance_predictions()

    assert "residuo" in out.columns
    _clear_caches()


def test_load_post_performance_predictions_returns_empty_dataframe_when_missing(
    tmp_path, monkeypatch
):
    _point_settings_at(monkeypatch, tmp_path)

    out = loaders.load_post_performance_predictions()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_posts_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    posts_path = settings.SILVER_DIR / "posts_clean"
    df = pd.DataFrame(
        {
            "id": ["p1"],
            "ownerUsername": ["g"],
            "inputUrl": ["https://www.instagram.com/g/"],
            "commentsCount": [1],
            "likesCount": [2],
            "_run_id": ["r1"],
        }
    )
    write_deltalake(str(posts_path), df, mode="overwrite")

    out = loaders.load_posts()

    assert "likesCount" in out.columns
    _clear_caches()


def test_load_posts_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = loaders.load_posts()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


# ADR 0020 (Frente 2) / issue #94: loaders novos das métricas de growth --
# mesmo par de testes (dado real + ausência) de todos os loaders acima.
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

    out = loaders.load_discourse_topics()

    assert "Name" in out.columns
    _clear_caches()


def test_load_discourse_topics_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = loaders.load_discourse_topics()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_topic_priority_score_returns_delta_table(tmp_path, monkeypatch):
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

    out = loaders.load_topic_priority_score()

    assert "score" in out.columns
    _clear_caches()


def test_load_topic_priority_score_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = loaders.load_topic_priority_score()

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

    out = loaders.load_nsm()

    assert "nsm" in out.columns
    _clear_caches()


def test_load_nsm_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = loaders.load_nsm()

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
            "ilustrativo": [True],
            "nota": ["ilustrativo"],
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    write_deltalake(str(path), df, mode="overwrite")

    out = loaders.load_growth_metrics()

    assert "cmgr" in out.columns
    _clear_caches()


def test_load_growth_metrics_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = loaders.load_growth_metrics()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()


def test_load_ugc_mentions_returns_delta_table(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)
    path = settings.GOLD_DIR / "governor_ugc_mentions"
    df = pd.DataFrame(
        {
            "id": ["u1"],
            "governor_username": ["governador_a"],
            "likesCount": [10],
            "commentsCount": [2],
            "is_organic": [True],
            "data_hora": pd.to_datetime(["2026-05-01"]),
            "_run_id": ["r1"],
            "_generated_at": pd.to_datetime(["2026-05-01"], utc=True),
        }
    )
    write_deltalake(str(path), df, mode="overwrite")

    out = loaders.load_ugc_mentions()

    assert "governor_username" in out.columns
    _clear_caches()


def test_load_ugc_mentions_returns_empty_dataframe_when_missing(tmp_path, monkeypatch):
    _point_settings_at(monkeypatch, tmp_path)

    out = loaders.load_ugc_mentions()

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    _clear_caches()
