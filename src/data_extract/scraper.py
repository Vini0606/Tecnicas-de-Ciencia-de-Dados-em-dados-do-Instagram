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
    # None: sem teto (Coleta, ADR 0043). `resultsLimit` é opcional nos actors de posts, reels e UGC (só `username` é
    # obrigatório no schema), então sem teto o campo é omitido e vale o comportamento do actor.
    results_limit: int | None = 30
    # Teto só do UGC (ADR 0044): o actor de UGC não filtra por data, então o limite é o único freio dele. None: vale
    # `results_limit`.
    results_limit_ugc: int | None = None
    # ADR 0020 (Ficha 3) / issue #88: `includeTranscript` é uma flag paga do
    # `apify/instagram-reel-scraper`, cobrada por minuto de vídeo transcrito
    # (achado de `docs/research/apify-instagram-actors-cobra-mapping.md`,
    # §1.2) -- mesmo padrão de flag paga que `includeSharesCount` (também
    # não habilitada hoje). Default False de propósito: o piloto pequeno
    # (1-2 perfis) descrito na issue precisa confirmar custo real e taxa de
    # reels sem transcrição disponível antes de ligar para os 27 perfis.
    include_transcript: bool = False

    @property
    def limite_input(self) -> dict:
        """`resultsLimit` dos actors de posts, reels e UGC: o teto, ou nada (campo omitido) sem teto."""
        return {} if self.results_limit is None else {"resultsLimit": self.results_limit}

    @property
    def limite_input_ugc(self) -> dict:
        """`resultsLimit` do actor de UGC: o teto próprio, senão o de `limite_input`."""
        if self.results_limit_ugc is not None:
            return {"resultsLimit": self.results_limit_ugc}
        return self.limite_input


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
        try:
            run = self._client.actor(actor_id).call(run_input=run_input)
            itens = list(self._client.dataset(run["defaultDatasetId"]).iterate_items())
        except Exception:
            # chamada que falhou pode já ter gastado: registra custo ilegível, para o custo real
            # da Coleta ficar nulo em vez de uma soma parcial (a ingestão tolera falha do UGC)
            self.execucoes.append({"colecao": colecao, "usd": None, "itens": 0})
            raise
        self.execucoes.append({"colecao": colecao, "usd": self._custo_final(run), "itens": len(itens)})
        return itens

    def _custo_final(self, run: dict) -> float | None:
        """Custo da execução já finalizada: `usageTotalUsd`; se a Apify ainda não o calculou, os eventos
        cobrados x o preço de cada evento da própria execução. `None` se nenhum dos dois for legível
        (nunca inventa valor)."""
        try:
            final = self._client.run(run.get("id")).get() or {}
        except Exception:  # noqa: BLE001 - custo é só registro: falhar aqui não pode derrubar a extração
            return None
        usd = final.get("usageTotalUsd")
        if isinstance(usd, (int, float)) and not isinstance(usd, bool):
            return float(usd)
        return self._custo_por_eventos(final)

    @staticmethod
    def _custo_por_eventos(run: dict) -> float | None:
        """`chargedEventCounts` x `pricingInfo...eventPriceUsd` (confere com o `usageTotalUsd` em runs reais)."""
        contagens = run.get("chargedEventCounts")
        info = run.get("pricingInfo")
        eventos = ((info or {}).get("pricingPerEvent") or {}).get("actorChargeEvents") if isinstance(info, dict) else None
        if not isinstance(contagens, dict) or not isinstance(eventos, dict):
            return None
        total = 0.0
        for evento, n in contagens.items():
            if not n:
                continue
            preco = (eventos.get(evento) or {}).get("eventPriceUsd")
            if isinstance(preco, bool) or not isinstance(preco, (int, float)) or isinstance(n, bool):
                return None
            total += n * preco
        return round(total, 6)

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
            **self._config.limite_input,
            **(extra_run_input or {}),
        }
        return self._rodar("posts", self._config.posts_actor_id, run_input)

    def scrape_reels(
        self, usernames: list[str], extra_run_input: dict | None = None
    ) -> list[dict]:
        run_input = {
            "username": usernames,
            **self._config.limite_input,
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
            **self._config.limite_input_ugc,
            **(extra_run_input or {}),
        }
        return self._rodar("ugc", self._config.mentions_actor_id, run_input)
