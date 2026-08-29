import json

import numpy as np
import pandas as pd


def _perfis_com_dois_grupos_separados():
    rng = np.random.default_rng(0)
    grupo_a = rng.normal(loc=0.0, scale=0.1, size=(4, 3))
    grupo_b = rng.normal(loc=5.0, scale=0.1, size=(4, 3))
    pontos = np.vstack([grupo_a, grupo_b])
    df = pd.DataFrame(pontos, columns=["% ENGAJAMENTO", "RECENCIA", "FREQUENCIA"])
    df["inputUrl"] = [f"https://www.instagram.com/g{i}/" for i in range(len(df))]
    return df


def test_model_handler(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "dummy-bucket")

    class DummyDT:
        def __init__(self, table_uri, *a, **k):
            self.table_uri = str(table_uri)

        def to_pandas(self):
            assert "governor_engagement" in self.table_uri
            return _perfis_com_dois_grupos_separados()

    monkeypatch.setattr("deltalake.DeltaTable", DummyDT)

    # Stub gold writer para evitar escrita real no S3/Delta.
    monkeypatch.setattr(
        "src.features.gold.model_enricher.write_delta", lambda *a, **k: None
    )

    from lambdas.model import handler as model_handler

    resp = model_handler.handler({"run_id": "test-run"}, {})
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("run_id") == "test-run"
    assert body.get("status") == "profile_clusters_engagement_complete"


def test_model_handler_missing_bucket(monkeypatch):
    monkeypatch.delenv("S3_BUCKET", raising=False)

    from lambdas.model import handler as model_handler

    resp = model_handler.handler({"run_id": "test-run"}, {})
    assert resp["statusCode"] == 400
    assert "body" in resp


def test_model_handler_missing_run_id(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "dummy-bucket")

    from lambdas.model import handler as model_handler

    resp = model_handler.handler({}, {})
    assert resp["statusCode"] == 400
    assert "body" in resp
