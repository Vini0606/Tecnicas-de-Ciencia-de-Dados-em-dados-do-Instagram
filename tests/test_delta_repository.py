import pandas as pd
from deltalake.writer import write_deltalake

from src.repositories.delta_repository import DeltaRepository


def test_delta_repository_basic(tmp_path):
    gold = tmp_path
    engagement_path = gold / "governor_engagement"
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

    repo = DeltaRepository(gold_dir=gold)
    out = repo.load_profiles()
    assert "% ENGAJAMENTO" in out.columns
