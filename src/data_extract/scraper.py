from __future__ import annotations

from dataclasses import dataclass

from apify_client import ApifyClient


@dataclass
class ScraperConfig:
    """Configuração injetável do scraper — sem hardcode de IDs de Actor."""

    profiles_actor_id: str = "shu8hvrXbJbY3Eb9W"
    posts_actor_id: str = "apify/instagram-post-scraper"
    reels_actor_id: str = "apify/instagram-reel-scraper"
    # ADR 0020 (Ficha 8) / issue #93: UGC de criação -- posts de terceiros que
    # marcam/mencionam o perfil do governador (nível "Creating" do COBRA).
    # `apify/instagram-tagged-scraper` foi escolhido sobre
    # `fetch_cat/instagram-mentions-scraper` por reprodutibilidade (oficial,
    # 9.999 usuários, 5.0*, vs. actor "under maintenance" com 2 usuários --
    # ver docs/research/apify-instagram-actors-cobra-mapping.md, §7).
    mentions_actor_id: str = "apify/instagram-tagged-scraper"
    results_limit: int = 30
    # ADR 0020 (Ficha 3) / issue #88: `includeTranscript` é uma flag paga do
    # `apify/instagram-reel-scraper`, cobrada por minuto de vídeo transcrito
    # (achado de `docs/research/apify-instagram-actors-cobra-mapping.md`,
    # §1.2) -- mesmo padrão de flag paga que `includeSharesCount` (também
    # não habilitada hoje). Default False de propósito: o piloto pequeno
    # (1-2 perfis) descrito na issue precisa confirmar custo real e taxa de
    # reels sem transcrição disponível antes de ligar para os 27 perfis.
    include_transcript: bool = False


class InstagramScraper:
    """
    Responsabilidade única: comunicar com a API Apify e retornar dados brutos.
    Não salva arquivos, não transforma dados.
    """

    def __init__(self, client: ApifyClient, config: ScraperConfig | None = None):
        self._client = client
        self._config = config or ScraperConfig()
        # Uma entrada por chamada paga (issue #297): coleção, custo final em US$ e itens devolvidos.
        self.execucoes: list[dict] = []

    def _rodar(self, colecao: str, actor_id: str, run_input: dict) -> list[dict]:
        """Chama o actor, lê os itens e registra o custo da execução finalizada."""
        run = self._client.actor(actor_id).call(run_input=run_input)
        itens = list(self._client.dataset(run["defaultDatasetId"]).iterate_items())
        self.execucoes.append({"colecao": colecao, "usd": self._custo_final(run), "itens": len(itens)})
        return itens

    def _custo_final(self, run: dict) -> float | None:
        """`usageTotalUsd` da execução já finalizada; `None` se não for legível (nunca inventa valor)."""
        try:
            final = self._client.run(run.get("id")).get() or {}
            usd = final.get("usageTotalUsd")
        except Exception:  # custo é só registro: falhar aqui não pode derrubar a extração
            return None
        if isinstance(usd, bool) or not isinstance(usd, (int, float)):
            return None
        return float(usd)

    def scrape_profiles(self, links: list[str]) -> list[dict]:
        run_input = {
            "directUrls": links,
            "addParentData": False,
            "resultsLimit": 100,
            "resultsType": "details",
            "searchType": "user",
        }
        return self._rodar("perfis", self._config.profiles_actor_id, run_input)

    def scrape_posts(
        self, usernames: list[str], extra_run_input: dict | None = None
    ) -> list[dict]:
        run_input = {
            "username": usernames,
            "resultsLimit": self._config.results_limit,
            **(extra_run_input or {}),
        }
        return self._rodar("posts", self._config.posts_actor_id, run_input)

    def scrape_reels(
        self, usernames: list[str], extra_run_input: dict | None = None
    ) -> list[dict]:
        run_input = {
            "username": usernames,
            "resultsLimit": self._config.results_limit,
            # `includeTranscript` só entra quando `ScraperConfig.include_transcript`
            # está ligado (ADR 0020 Ficha 3 / issue #88) -- `extra_run_input`
            # abaixo ainda pode sobrescrever, mesmo padrão de `resultsLimit`.
            **({"includeTranscript": True} if self._config.include_transcript else {}),
            **(extra_run_input or {}),
        }
        return self._rodar("reels", self._config.reels_actor_id, run_input)

    def scrape_mentions(
        self, usernames: list[str], extra_run_input: dict | None = None
    ) -> list[dict]:
        """UGC de criação (ADR 0020, Ficha 8 / issue #93): posts de terceiros
        que marcam/mencionam `usernames` -- não conteúdo publicado pelo
        próprio perfil. Mesmo padrão de `scrape_posts`/`scrape_reels`
        (`username`/`resultsLimit` no `run_input`, `extra_run_input` tem a
        última palavra). Rodar com `results_limit` baixo (piloto, via
        `coleta.py coletar --teto N`) antes de qualquer coleta em
        volume -- os nomes exatos de campo do actor ainda não foram
        confirmados contra os 27 perfis reais do projeto."""
        run_input = {
            "username": usernames,
            "resultsLimit": self._config.results_limit,
            **(extra_run_input or {}),
        }
        return self._rodar("ugc", self._config.mentions_actor_id, run_input)
