from __future__ import annotations

from dataclasses import dataclass

from apify_client import ApifyClient


@dataclass
class ScraperConfig:
    """Configuração injetável do scraper — sem hardcode de IDs de Actor."""

    profiles_actor_id: str = "shu8hvrXbJbY3Eb9W"
    posts_actor_id: str = "apify/instagram-post-scraper"
    reels_actor_id: str = "apify/instagram-reel-scraper"
    results_limit: int = 30


class InstagramScraper:
    """
    Responsabilidade única: comunicar com a API Apify e retornar dados brutos.
    Não salva arquivos, não transforma dados.
    """

    def __init__(self, client: ApifyClient, config: ScraperConfig | None = None):
        self._client = client
        self._config = config or ScraperConfig()

    def scrape_profiles(self, links: list[str]) -> list[dict]:
        run_input = {
            "directUrls": links,
            "addParentData": False,
            "resultsLimit": 100,
            "resultsType": "details",
            "searchType": "user",
        }
        run = self._client.actor(self._config.profiles_actor_id).call(
            run_input=run_input
        )
        return list(self._client.dataset(run["defaultDatasetId"]).iterate_items())

    def scrape_posts(self, usernames: list[str]) -> list[dict]:
        run_input = {"username": usernames, "resultsLimit": self._config.results_limit}
        run = self._client.actor(self._config.posts_actor_id).call(run_input=run_input)
        return list(self._client.dataset(run["defaultDatasetId"]).iterate_items())

    def scrape_reels(self, usernames: list[str]) -> list[dict]:
        run_input = {"username": usernames, "resultsLimit": self._config.results_limit}
        run = self._client.actor(self._config.reels_actor_id).call(run_input=run_input)
        return list(self._client.dataset(run["defaultDatasetId"]).iterate_items())
