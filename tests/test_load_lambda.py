import json
from unittest.mock import MagicMock

import pandas as pd


def make_parquet_bytes(df: pd.DataFrame):
    import io

    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    return buf.getvalue()


def test_load_handler(monkeypatch):
    df = pd.DataFrame({"id": ["1"], "followersCount": [100]})
    parquet_bytes = make_parquet_bytes(df)

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=parquet_bytes))
    }
    fake_s3.put_object.return_value = {}

    monkeypatch.setattr("boto3.client", MagicMock(return_value=fake_s3))
    monkeypatch.setenv("S3_BUCKET", "dummy-bucket")

    # Patch deltalake.DeltaTable to avoid real S3 calls

    class DummyDT:
        def __init__(self, table_uri, *a, **k):
            self.table_uri = str(table_uri)

        def to_pandas(self):
            if (
                "profiles_clean" in self.table_uri
                or "governor_engagement" in self.table_uri
            ):
                return pd.DataFrame(
                    {
                        "id": ["1"],
                        "username": ["g"],
                        "followersCount": [100],
                        "TOTAL ENGAJAMENTO": [10],
                        "% ENGAJAMENTO": [0.1],
                    }
                )
            if "posts_clean" in self.table_uri:
                return pd.DataFrame(
                    {
                        "ownerId": ["1"],
                        "ownerUsername": ["g"],
                        "commentsCount": [1],
                        "likesCount": [2],
                        "data_hora": pd.to_datetime(["2026-05-01"]),
                    }
                )
            if "reels_clean" in self.table_uri:
                return pd.DataFrame(
                    {
                        "ownerId": ["1"],
                        "ownerUsername": ["g"],
                        "commentsCount": [2],
                        "likesCount": [3],
                        "data_hora": pd.to_datetime(["2026-05-02"]),
                    }
                )
            return pd.DataFrame()

    monkeypatch.setattr("deltalake.DeltaTable", DummyDT)

    # Stub gold writer to avoid real Delta writes
    monkeypatch.setattr(
        "src.features.gold.engagement_aggregator.write_deltalake", lambda *a, **k: None
    )

    from lambdas.load import handler as load_handler

    resp = load_handler.handler({"run_id": "test-run"}, {})
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("run_id") == "test-run"
    assert body.get("status") == "gold_complete"


def test_load_handler_missing_bucket(monkeypatch):
    monkeypatch.delenv("S3_BUCKET", raising=False)

    from lambdas.load import handler as load_handler

    resp = load_handler.handler({}, {})
    assert resp["statusCode"] == 400
    assert "body" in resp
