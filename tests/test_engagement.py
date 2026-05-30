import pandas as pd
import pytest

from src.features.engagement import EngagementFeatureBuilder


@pytest.fixture
def sample_data():
    df_profiles = pd.DataFrame(
        {
            "id": ["1", "2"],
            "followersCount": [1000, 2000],
        }
    )
    df_posts = pd.DataFrame(
        {
            "ownerId": ["1", "2"],
            "ownerUsername": ["user1", "user2"],
            "commentsCount": [10, 20],
            "likesCount": [100, 200],
            "timestamp": ["2024-01-01T12:00:00+00:00", "2024-01-02T12:00:00+00:00"],
        }
    )
    df_reels = df_posts.copy()
    df_reels["dimensionsWidth"] = 1080
    df_reels["dimensionsHeight"] = 1920
    return df_profiles, df_posts, df_reels


def test_engagement_columns_created(sample_data):
    builder = EngagementFeatureBuilder()
    df, _ = builder.build(*sample_data)
    assert "TOTAL ENGAJAMENTO" in df.columns
    assert "% ENGAJAMENTO" in df.columns
    assert "RECENCIA" in df.columns
    assert "FREQUENCIA" in df.columns


def test_engagement_not_negative(sample_data):
    builder = EngagementFeatureBuilder()
    df, _ = builder.build(*sample_data)
    assert (df["% ENGAJAMENTO"].dropna() >= 0).all()
