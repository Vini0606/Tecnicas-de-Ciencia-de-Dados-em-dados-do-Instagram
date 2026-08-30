from pathlib import Path

import pytest

from src.data_extract.ingestion import archive_raw_json, extract_and_land


class _FakeScraper:
    def __init__(self):
        self.posts_calls = []
        self.reels_calls = []

    def scrape_profiles(self, links):
        return [{"inputUrl": "https://instagram.com/gov1", "username": "gov1"}]

    def scrape_posts(self, links, extra_run_input=None):
        self.posts_calls.append((links, extra_run_input))
        return [{"inputUrl": "https://instagram.com/gov1", "id": "p1"}]

    def scrape_reels(self, links, extra_run_input=None):
        self.reels_calls.append((links, extra_run_input))
        return [{"inputUrl": "https://instagram.com/gov1", "id": "r1"}]


class _FakeBronzeWriter:
    def __init__(self):
        self.calls = []

    def write_profiles(self, raw_data, run_id=None):
        self.calls.append(("profiles", raw_data, run_id))

    def write_posts(self, raw_data, run_id=None):
        self.calls.append(("posts", raw_data, run_id))

    def write_reels(self, raw_data, run_id=None):
        self.calls.append(("reels", raw_data, run_id))


class _OrderCheckingBronzeWriter:
    """Falha se a Bronze receber uma entidade antes dela existir na landing zone."""

    def __init__(self, landing_dir):
        self.landing_dir = Path(landing_dir)
        self.write_order = []

    def _assert_archived(self, entity, run_id):
        assert (self.landing_dir / run_id / f"{entity}.json").exists(), (
            f"{entity} foi escrito na Bronze antes de ser arquivado na landing zone"
        )

    def write_profiles(self, raw_data, run_id=None):
        self._assert_archived("profiles", run_id)
        self.write_order.append("profiles")

    def write_posts(self, raw_data, run_id=None):
        self._assert_archived("posts", run_id)
        self.write_order.append("posts")

    def write_reels(self, raw_data, run_id=None):
        self._assert_archived("reels", run_id)
        self.write_order.append("reels")


def test_archive_raw_json_grava_json_bruto_por_run_id_e_entidade(tmp_path):
    path = archive_raw_json(tmp_path, "posts", [{"id": "p1"}], run_id="run_1")

    assert path == tmp_path / "run_1" / "posts.json"
    assert path.exists()
    assert '"id": "p1"' in path.read_text(encoding="utf-8")


def test_extract_and_land_arquiva_e_escreve_as_tres_entidades_sob_o_mesmo_run_id(tmp_path):
    scraper = _FakeScraper()
    bronze = _FakeBronzeWriter()

    result = extract_and_land(
        scraper, bronze, tmp_path, links=["https://instagram.com/gov1"], run_id="run_fixo"
    )

    assert {kind for kind, _, _ in bronze.calls} == {"profiles", "posts", "reels"}
    assert all(run_id == "run_fixo" for _, _, run_id in bronze.calls)
    assert (tmp_path / "run_fixo" / "profiles.json").exists()
    assert (tmp_path / "run_fixo" / "posts.json").exists()
    assert (tmp_path / "run_fixo" / "reels.json").exists()
    assert result["profiles"][0]["username"] == "gov1"
    assert result["posts"][0]["id"] == "p1"
    assert result["reels"][0]["id"] == "r1"


def test_extract_and_land_propaga_extra_run_input_so_para_posts_e_reels(tmp_path):
    scraper = _FakeScraper()
    bronze = _FakeBronzeWriter()

    extract_and_land(
        scraper,
        bronze,
        tmp_path,
        links=["https://instagram.com/gov1"],
        run_id="run_1",
        extra_run_input={"onlyPostsNewerThan": "90 days"},
    )

    assert scraper.posts_calls[0][1] == {"onlyPostsNewerThan": "90 days"}
    assert scraper.reels_calls[0][1] == {"onlyPostsNewerThan": "90 days"}


def test_extract_and_land_arquiva_cada_entidade_antes_de_escreve_la_na_bronze(tmp_path):
    scraper = _FakeScraper()
    bronze = _OrderCheckingBronzeWriter(tmp_path)

    extract_and_land(scraper, bronze, tmp_path, links=["l"], run_id="run_1")

    assert bronze.write_order == ["profiles", "posts", "reels"]


class _BronzeWriterFalhandoEmReels:
    """Simula uma falha na escrita da Bronze pra reels, depois de
    profiles/posts terem sido escritos com sucesso."""

    def write_profiles(self, raw_data, run_id=None):
        pass

    def write_posts(self, raw_data, run_id=None):
        pass

    def write_reels(self, raw_data, run_id=None):
        raise RuntimeError("falha simulada na escrita da Bronze")


def test_extract_and_land_preserva_o_arquivado_mesmo_se_a_bronze_falhar(tmp_path):
    """Cenario descrito no spec (issue #31): uma falha na escrita da Bronze
    para uma entidade nao deve apagar o JSON bruto ja arquivado das
    entidades anteriores (nem da propria entidade que falhou, ja arquivada
    antes da tentativa de escrita)."""
    scraper = _FakeScraper()
    bronze = _BronzeWriterFalhandoEmReels()

    with pytest.raises(RuntimeError, match="falha simulada"):
        extract_and_land(scraper, bronze, tmp_path, links=["l"], run_id="run_1")

    assert (tmp_path / "run_1" / "profiles.json").exists()
    assert (tmp_path / "run_1" / "posts.json").exists()
    assert (tmp_path / "run_1" / "reels.json").exists()
