import pandas as pd

from src.features.silver.comment_cleaner import CommentCleaner
from src.features.silver.post_cleaner import PostCleaner
from src.features.silver.profile_cleaner import ProfileCleaner


def test_profile_cleaner_basic():
    df = pd.DataFrame(
        {
            "id": ["1"],
            "username": ["g"],
            "followersCount": [100],
            "_ingested_at": pd.to_datetime(["2026-05-01"], utc=True),
            "_run_id": ["r1"],
        }
    )
    cleaner = ProfileCleaner()
    out = cleaner.clean(df, run_id="r1")
    assert "_source_layer" in out.columns


def test_profile_cleaner_adds_fullname_when_missing():
    df = pd.DataFrame(
        {
            "id": ["1"],
            "username": ["g"],
            "followersCount": [100],
            "_ingested_at": pd.to_datetime(["2026-05-01"], utc=True),
            "_run_id": ["r1"],
        }
    )
    cleaner = ProfileCleaner()
    out = cleaner.clean(df, run_id="r1")
    assert "fullName" in out.columns
    assert out.loc[0, "fullName"] == "g"


def test_post_cleaner_feed_and_reel():
    df_posts = pd.DataFrame(
        {
            "id": ["p1"],
            "ownerId": ["1"],
            "ownerUsername": ["g"],
            "commentsCount": [1],
            "likesCount": [2],
            "timestamp": ["2026-05-01T00:00:00+00:00"],
            "_ingested_at": pd.to_datetime(["2026-05-01"], utc=True),
            "_run_id": ["r1"],
        }
    )
    pc = PostCleaner()
    outp = pc.clean_posts(df_posts)
    assert (outp["Tipo"] == "FEED").all()

    df_reels = pd.DataFrame(
        {
            "id": ["r1"],
            "ownerId": ["1"],
            "ownerUsername": ["g"],
            "commentsCount": [1],
            "likesCount": [2],
            "timestamp": ["2026-05-01T00:00:00+00:00"],
            "latestComments": ["[]"],
            "_ingested_at": pd.to_datetime(["2026-05-01"], utc=True),
            "_run_id": ["r1"],
        }
    )
    outr = pc.clean_reels(df_reels)
    assert (outr["Tipo"] == "REELS").all()


def test_comment_cleaner_explode():
    df_reels = pd.DataFrame(
        {"id": ["r1"], "latestComments": ['[{"id": "c1", "text": "ok"}]']}
    )
    cc = CommentCleaner()
    out = cc.clean(df_reels)
    assert not out.empty
