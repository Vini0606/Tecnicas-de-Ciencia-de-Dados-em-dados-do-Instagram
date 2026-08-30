from unittest.mock import MagicMock


class _FakeInstagramScraper:
    def __init__(self, client, config):
        self.client = client
        self.config = config
        self.posts_extra_run_input = None
        self.reels_extra_run_input = None

    def scrape_profiles(self, links):
        return [{"inputUrl": "https://instagram.com/gov1", "username": "gov1"}]

    def scrape_posts(self, links, extra_run_input=None):
        self.posts_extra_run_input = extra_run_input
        return [{"inputUrl": "https://instagram.com/gov1", "id": "p1"}]

    def scrape_reels(self, links, extra_run_input=None):
        self.reels_extra_run_input = extra_run_input
        return [{"inputUrl": "https://instagram.com/gov1", "id": "r1"}]


def _fake_bronze_writer_class(calls):
    class FakeBronzeWriter:
        def __init__(self, **kwargs):
            pass

        def write_profiles(self, raw_data, run_id=None):
            calls.append(("profiles", raw_data, run_id))
            return run_id

        def write_posts(self, raw_data, run_id=None):
            calls.append(("posts", raw_data, run_id))
            return run_id

        def write_reels(self, raw_data, run_id=None):
            calls.append(("reels", raw_data, run_id))
            return run_id

    return FakeBronzeWriter


def _patch_backfill_dependencies(monkeypatch, tmp_path, scraper_class=_FakeInstagramScraper):
    calls = []
    monkeypatch.setattr("scripts.run_apify_backfill.BronzeWriter", _fake_bronze_writer_class(calls))
    monkeypatch.setattr("scripts.run_apify_backfill.InstagramScraper", scraper_class)
    monkeypatch.setattr("scripts.run_apify_backfill.ApifyClient", lambda token: MagicMock())
    monkeypatch.setattr(
        "scripts.run_apify_backfill.load_links", lambda: ["https://instagram.com/gov1"]
    )
    monkeypatch.setattr("scripts.run_apify_backfill.BACKFILL_REPORT_DIR", tmp_path)
    return calls


def test_run_escreve_profiles_posts_reels_na_bronze_sob_o_mesmo_run_id(monkeypatch, tmp_path):
    import scripts.run_apify_backfill as backfill_script

    calls = _patch_backfill_dependencies(monkeypatch, tmp_path)

    report = backfill_script.run(
        apify_api_token="token", days=365, results_limit=5000, run_id="run_fixo"
    )

    assert report["run_id"] == "run_fixo"
    assert len(calls) == 3
    assert {kind for kind, _, _ in calls} == {"profiles", "posts", "reels"}
    assert all(run_id == "run_fixo" for _, _, run_id in calls)


def test_run_gera_run_id_quando_nao_informado(monkeypatch, tmp_path):
    import scripts.run_apify_backfill as backfill_script

    calls = _patch_backfill_dependencies(monkeypatch, tmp_path)

    report = backfill_script.run(apify_api_token="token", days=90, results_limit=1000)

    assert report["run_id"]
    assert all(run_id == report["run_id"] for _, _, run_id in calls)


def test_run_nao_grava_json_bruto_de_itens_so_o_relatorio(monkeypatch, tmp_path):
    import scripts.run_apify_backfill as backfill_script

    _patch_backfill_dependencies(monkeypatch, tmp_path)

    backfill_script.run(apify_api_token="token", days=90, results_limit=1000)

    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name.startswith("backfill_report_")


def test_run_propaga_only_posts_newer_than_para_posts_e_reels_nao_para_profiles(
    monkeypatch, tmp_path
):
    import scripts.run_apify_backfill as backfill_script

    scraper_instances = []

    class _CapturingScraper(_FakeInstagramScraper):
        def __init__(self, client, config):
            super().__init__(client, config)
            scraper_instances.append(self)

    _patch_backfill_dependencies(monkeypatch, tmp_path, scraper_class=_CapturingScraper)

    backfill_script.run(apify_api_token="token", days=180, results_limit=2000)

    scraper = scraper_instances[0]
    assert scraper.posts_extra_run_input == {"onlyPostsNewerThan": "180 days"}
    assert scraper.reels_extra_run_input == {"onlyPostsNewerThan": "180 days"}
