import pytest

from src.data_extract.ingestion import extract_and_land


class _FakeScraper:
    def __init__(self):
        self.posts_calls = []
        self.reels_calls = []
        self.mentions_calls = []

    def scrape_profiles(self, links):
        return [{"inputUrl": "https://instagram.com/gov1", "username": "gov1"}]

    def scrape_posts(self, links, extra_run_input=None):
        self.posts_calls.append((links, extra_run_input))
        return [{"inputUrl": "https://instagram.com/gov1", "id": "p1"}]

    def scrape_reels(self, links, extra_run_input=None):
        self.reels_calls.append((links, extra_run_input))
        return [{"inputUrl": "https://instagram.com/gov1", "id": "r1"}]

    def scrape_mentions(self, links, extra_run_input=None):
        self.mentions_calls.append((links, extra_run_input))
        return [{"inputUrl": "https://instagram.com/gov1", "id": "m1"}]


class _FakeBronzeWriter:
    def __init__(self):
        self.calls = []

    def write_profiles(self, raw_data, run_id=None):
        self.calls.append(("profiles", raw_data, run_id))

    def write_posts(self, raw_data, run_id=None):
        self.calls.append(("posts", raw_data, run_id))

    def write_reels(self, raw_data, run_id=None):
        self.calls.append(("reels", raw_data, run_id))

    def write_ugc_mentions(self, raw_data, run_id=None):
        self.calls.append(("ugc_mentions", raw_data, run_id))


def test_extract_and_land_escreve_as_quatro_entidades_sob_o_mesmo_run_id():
    scraper = _FakeScraper()
    bronze = _FakeBronzeWriter()

    result = extract_and_land(
        scraper, bronze, links=["https://instagram.com/gov1"], run_id="run_fixo"
    )

    assert [kind for kind, _, _ in bronze.calls] == [
        "profiles",
        "posts",
        "reels",
        "ugc_mentions",
    ]
    assert all(run_id == "run_fixo" for _, _, run_id in bronze.calls)
    assert result["profiles"][0]["username"] == "gov1"
    assert result["posts"][0]["id"] == "p1"
    assert result["reels"][0]["id"] == "r1"
    assert result["ugc_mentions"][0]["id"] == "m1"
    assert "ugc_error" not in result


def test_extract_and_land_propaga_extra_run_input_para_posts_reels_e_ugc():
    scraper = _FakeScraper()
    bronze = _FakeBronzeWriter()

    extract_and_land(
        scraper,
        bronze,
        links=["https://instagram.com/gov1"],
        run_id="run_1",
        extra_run_input={"onlyPostsNewerThan": "90 days"},
    )

    assert scraper.posts_calls[0][1] == {"onlyPostsNewerThan": "90 days"}
    assert scraper.reels_calls[0][1] == {"onlyPostsNewerThan": "90 days"}
    assert scraper.mentions_calls[0][1] == {"onlyPostsNewerThan": "90 days"}


class _BronzeWriterFalhandoEmReels:
    """Simula uma falha na escrita da Bronze pra reels, depois de
    profiles/posts terem sido escritos com sucesso."""

    def __init__(self):
        self.escritos = []

    def write_profiles(self, raw_data, run_id=None):
        self.escritos.append("profiles")

    def write_posts(self, raw_data, run_id=None):
        self.escritos.append("posts")

    def write_reels(self, raw_data, run_id=None):
        raise RuntimeError("falha simulada na escrita da Bronze")


def test_extract_and_land_propaga_falha_da_bronze_sem_desfazer_o_que_ja_foi_escrito():
    """Perfis e posts já gravados continuam gravados quando reels falha: a
    exceção sobe (fail-fast) e nada é revertido. Não há landing separada --
    o item bruto já está na própria Bronze (ADR 0039)."""
    bronze = _BronzeWriterFalhandoEmReels()

    with pytest.raises(RuntimeError, match="falha simulada"):
        extract_and_land(_FakeScraper(), bronze, links=["l"], run_id="run_1")

    assert bronze.escritos == ["profiles", "posts"]


class _ScraperComUgcFalhando(_FakeScraper):
    def scrape_mentions(self, links, extra_run_input=None):
        raise RuntimeError("actor de UGC indisponivel")


class _ScraperComUgcVazio(_FakeScraper):
    def scrape_mentions(self, links, extra_run_input=None):
        return []


class _BronzeWriterSemUgc(_FakeBronzeWriter):
    """Espelha o BronzeWriter real construido sem `bronze_ugc_mentions_path`
    (KeyError ao gravar UGC)."""

    def write_ugc_mentions(self, raw_data, run_id=None):
        raise KeyError("ugc_mentions")


@pytest.mark.parametrize(
    ("scraper", "bronze"),
    [
        (_ScraperComUgcFalhando(), _FakeBronzeWriter()),
        (_ScraperComUgcVazio(), _FakeBronzeWriter()),
        (_FakeScraper(), _BronzeWriterSemUgc()),
    ],
    ids=["actor_falha", "lista_vazia", "bronze_sem_caminho_de_ugc"],
)
def test_extract_and_land_tolera_falha_de_ugc_sem_perder_as_demais_entidades(
    scraper, bronze
):
    """Issue #211: UGC e a ultima coleta e e tolerante a falha -- perfis,
    posts e reels (ja pagos e gravados) nunca sao descartados por ela."""
    result = extract_and_land(scraper, bronze, links=["l"], run_id="run_1")

    gravadas = [kind for kind, _, _ in bronze.calls]
    assert gravadas[:3] == ["profiles", "posts", "reels"]
    assert "ugc_mentions" not in gravadas
    assert result["ugc_mentions"] == []
    assert result["ugc_error"]
    assert len(result["reels"]) == 1
