import json
from unittest.mock import MagicMock


def _fake_bronze_writer_class():
    class FakeBronzeWriter:
        def __init__(self, **kwargs):
            pass

        def write_profiles(self, *a, **k):
            pass

        def write_posts(self, *a, **k):
            pass

        def write_reels(self, *a, **k):
            pass

    return FakeBronzeWriter


def _patch_extract_dependencies(monkeypatch, profiles, posts, reels):
    fake_scraper = MagicMock()
    fake_scraper.scrape_profiles.return_value = profiles
    fake_scraper.scrape_posts.return_value = posts
    fake_scraper.scrape_reels.return_value = reels

    monkeypatch.setattr("lambdas.extract.handler.ApifyClient", lambda token: MagicMock())
    monkeypatch.setattr(
        "lambdas.extract.handler.InstagramScraper",
        lambda client, config: fake_scraper,
    )
    monkeypatch.setattr("lambdas.extract.handler.BronzeWriter", _fake_bronze_writer_class())
    return fake_scraper


def test_extract_handler(monkeypatch):
    from lambdas.extract import handler as extract_handler

    monkeypatch.setenv("APIFY_API_TOKEN", "token")
    monkeypatch.setenv("S3_BUCKET", "dummy-bucket")
    _patch_extract_dependencies(
        monkeypatch, profiles=[{"id": "1"}], posts=[{"id": "1"}], reels=[{"id": "1"}, {"id": "2"}]
    )

    resp = extract_handler.handler(
        {"links": ["https://www.instagram.com/exemplo/"], "run_id": "test-run"}, {}
    )

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body == {"run_id": "test-run", "profiles": 1, "posts": 1, "reels": 2}


def test_extract_handler_gera_run_id_quando_ausente(monkeypatch):
    from lambdas.extract import handler as extract_handler

    monkeypatch.setenv("APIFY_API_TOKEN", "token")
    monkeypatch.setenv("S3_BUCKET", "dummy-bucket")
    _patch_extract_dependencies(monkeypatch, profiles=[], posts=[], reels=[])

    resp = extract_handler.handler({"links": ["https://www.instagram.com/exemplo/"]}, {})

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["run_id"]


def test_extract_handler_sem_token_ou_bucket(monkeypatch):
    from lambdas.extract import handler as extract_handler

    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("S3_BUCKET", raising=False)

    resp = extract_handler.handler({"links": ["https://www.instagram.com/exemplo/"]}, {})

    assert resp["statusCode"] == 400


def test_extract_handler_sem_links(monkeypatch):
    from lambdas.extract import handler as extract_handler

    monkeypatch.setenv("APIFY_API_TOKEN", "token")
    monkeypatch.setenv("S3_BUCKET", "dummy-bucket")

    resp = extract_handler.handler({}, {})

    assert resp["statusCode"] == 400
