import json
from unittest.mock import MagicMock


def make_s3_mock(get_obj_data: bytes):
    s3 = MagicMock()
    s3.get_object.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=get_obj_data))
    }
    s3.put_object.return_value = {}
    return s3


def test_transform_handler(monkeypatch, tmp_path):
    # Prepare fake JSON data
    profiles = [{"id": "1", "followersCount": 100}]
    posts = [
        {
            "ownerId": "1",
            "ownerUsername": "u",
            "commentsCount": 1,
            "likesCount": 2,
            "timestamp": "2024-01-01T00:00:00+00:00",
        }
    ]
    reels = posts

    # Simulate S3 get_object returning JSON bytes sequentially for profiles, posts, reels
    payloads = [
        json.dumps(profiles).encode("utf-8"),
        json.dumps(posts).encode("utf-8"),
        json.dumps(reels).encode("utf-8"),
    ]

    call_index = {"i": 0}

    def fake_get_object(Bucket, Key):
        data = payloads[call_index["i"]]
        call_index["i"] += 1
        return {"Body": MagicMock(read=MagicMock(return_value=data))}

    fake_s3 = MagicMock()
    fake_s3.get_object.side_effect = fake_get_object
    fake_s3.put_object.return_value = {}

    monkeypatch.setattr("boto3.client", MagicMock(return_value=fake_s3))
    monkeypatch.setenv("S3_BUCKET", "dummy-bucket")

    # Prevent DeltaTable S3 access in BronzeWriter by patching its read methods
    import pandas as pd

    monkeypatch.setattr(
        "src.data_extract.bronze_writer.BronzeWriter.get_latest_profiles",
        lambda self: pd.DataFrame(profiles),
    )
    monkeypatch.setattr(
        "src.data_extract.bronze_writer.BronzeWriter.get_latest_posts",
        lambda self: pd.DataFrame(posts),
    )
    monkeypatch.setattr(
        "src.data_extract.bronze_writer.BronzeWriter.get_latest_reels",
        lambda self: pd.DataFrame(reels),
    )

    # Also patch deltalake.DeltaTable to avoid real S3 calls during writes

    class DummyDT:
        def __init__(self, table_uri, *a, **k):
            self.table_uri = str(table_uri)

        def to_pandas(self):
            if "profiles_clean" in self.table_uri:
                return pd.DataFrame({"id": ["1"], "followersCount": [100]})
            if "posts_clean" in self.table_uri:
                return pd.DataFrame(
                    {
                        "ownerId": ["1"],
                        "ownerUsername": ["u"],
                        "commentsCount": [1],
                        "likesCount": [2],
                        "data_hora": pd.to_datetime(["2024-01-01"]),
                    }
                )
            if "reels_clean" in self.table_uri:
                return pd.DataFrame(
                    {
                        "ownerId": ["1"],
                        "ownerUsername": ["u"],
                        "commentsCount": [1],
                        "likesCount": [2],
                        "data_hora": pd.to_datetime(["2024-01-01"]),
                    }
                )
            return pd.DataFrame()

    monkeypatch.setattr("deltalake.DeltaTable", DummyDT)

    # Stub writer calls in silver modules to avoid real Delta writes
    monkeypatch.setattr(
        "src.features.silver.profile_cleaner.write_deltalake", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "src.features.silver.post_cleaner.write_deltalake", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "src.features.silver.comment_cleaner.write_deltalake", lambda *a, **k: None
    )

    # Import handler and run
    from lambdas.transform import handler as transform_handler

    resp = transform_handler.handler({"run_id": "test-run"}, {})
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("run_id") == "test-run"
    assert body.get("status") == "silver_complete"


def test_transform_handler_missing_bucket(monkeypatch):
    monkeypatch.delenv("S3_BUCKET", raising=False)

    from lambdas.transform import handler as transform_handler

    resp = transform_handler.handler({}, {})
    assert resp["statusCode"] == 400
    assert "body" in resp
