"""Testes de scripts/run_ugc_mentions.py (ADR 0020, Ficha 8 / issue #93)."""

import json
from unittest.mock import MagicMock

import pandas as pd


class _FakeInstagramScraper:
    def __init__(self, client, config):
        self.client = client
        self.config = config
        self.mentions_extra_run_input = None

    def scrape_mentions(self, links, extra_run_input=None):
        self.mentions_extra_run_input = extra_run_input
        return [
            {
                "id": "m1",
                "shortCode": "abc123",
                "caption": "apoio total ao governador!",
                "mentions": json.dumps([]),
                "taggedUsers": json.dumps([{"username": "gov1"}]),
                "likesCount": 5,
                "commentsCount": 1,
                "timestamp": "2026-05-01T00:00:00+00:00",
                "ownerUsername": "eleitor_1",
                "paidPartnership": False,
            }
        ]


class _FakeDeltaRepository:
    def __init__(self, gold_dir, silver_dir):
        pass

    def load_profiles(self):
        return pd.DataFrame({"username": ["gov1"]})


def _patch_dependencies(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.run_ugc_mentions.InstagramScraper", _FakeInstagramScraper)
    monkeypatch.setattr("scripts.run_ugc_mentions.ApifyClient", lambda token: MagicMock())
    monkeypatch.setattr("scripts.run_ugc_mentions.DeltaRepository", _FakeDeltaRepository)
    monkeypatch.setattr(
        "scripts.run_ugc_mentions.load_links", lambda: ["https://instagram.com/gov1"]
    )
    monkeypatch.setattr("scripts.run_ugc_mentions.settings.LANDING_DIR", tmp_path / "landing")
    monkeypatch.setattr("scripts.run_ugc_mentions.settings.BRONZE_PROFILES", tmp_path / "b_profiles")
    monkeypatch.setattr("scripts.run_ugc_mentions.settings.BRONZE_POSTS", tmp_path / "b_posts")
    monkeypatch.setattr("scripts.run_ugc_mentions.settings.BRONZE_REELS", tmp_path / "b_reels")
    monkeypatch.setattr(
        "scripts.run_ugc_mentions.settings.BRONZE_UGC_MENTIONS", tmp_path / "b_ugc_mentions"
    )
    monkeypatch.setattr(
        "scripts.run_ugc_mentions.settings.SILVER_UGC_MENTIONS", tmp_path / "s_ugc_mentions"
    )
    monkeypatch.setattr(
        "scripts.run_ugc_mentions.settings.GOLD_UGC_MENTIONS", tmp_path / "g_ugc_mentions"
    )


def test_run_grava_bronze_silver_gold_sob_o_mesmo_run_id(monkeypatch, tmp_path):
    import scripts.run_ugc_mentions as ugc_script

    _patch_dependencies(monkeypatch, tmp_path)

    result = ugc_script.run(apify_api_token="token", results_limit=5, run_id="run_fixo")

    assert result["run_id"] == "run_fixo"
    assert result["raw_count"] == 1
    assert (tmp_path / "landing" / "run_fixo" / "ugc_mentions.json").exists()

    from deltalake import DeltaTable

    bronze_df = DeltaTable(str(tmp_path / "b_ugc_mentions")).to_pandas()
    assert (bronze_df["_run_id"] == "run_fixo").all()

    silver_df = DeltaTable(str(tmp_path / "s_ugc_mentions")).to_pandas()
    assert (silver_df["_run_id"] == "run_fixo").all()

    gold_df = DeltaTable(str(tmp_path / "g_ugc_mentions")).to_pandas()
    assert (gold_df["_run_id"] == "run_fixo").all()


def test_run_correlaciona_via_tagged_users(monkeypatch, tmp_path):
    """O item sintético só tem `taggedUsers` preenchido (mentions vazio) --
    confirma que o governor_username acaba resolvido na Gold, mesmo padrão
    do achado real do piloto (2026-09-19)."""
    import scripts.run_ugc_mentions as ugc_script

    _patch_dependencies(monkeypatch, tmp_path)

    result = ugc_script.run(apify_api_token="token", results_limit=5, run_id="run_fixo")

    assert result["n_correlacionados"] == 1

    from deltalake import DeltaTable

    gold_df = DeltaTable(str(tmp_path / "g_ugc_mentions")).to_pandas()
    assert gold_df.iloc[0]["governor_username"] == "gov1"
    assert bool(gold_df.iloc[0]["is_organic"]) is True


def test_run_propaga_results_limit_ao_scraper(monkeypatch, tmp_path):
    import scripts.run_ugc_mentions as ugc_script

    scraper_instances = []

    class _CapturingScraper(_FakeInstagramScraper):
        def __init__(self, client, config):
            super().__init__(client, config)
            scraper_instances.append(self)

    _patch_dependencies(monkeypatch, tmp_path)
    monkeypatch.setattr("scripts.run_ugc_mentions.InstagramScraper", _CapturingScraper)

    ugc_script.run(apify_api_token="token", results_limit=7, run_id="run_fixo")

    assert scraper_instances[0].config.results_limit == 7
