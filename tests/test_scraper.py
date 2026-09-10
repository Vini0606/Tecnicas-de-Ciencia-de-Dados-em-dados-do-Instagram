"""Testes de `InstagramScraper`/`ScraperConfig` -- foco nesta rodada (ADR
0020 Ficha 3 / issue #88) é a flag paga `includeTranscript` do
`apify/instagram-reel-scraper`, seguindo o mesmo padrão de configuração já
usado por `results_limit`."""

from unittest.mock import MagicMock

from src.data_extract.scraper import InstagramScraper, ScraperConfig


def _fake_client(dataset_items=None):
    client = MagicMock()
    actor_mock = MagicMock()
    actor_mock.call.return_value = {"defaultDatasetId": "d1"}
    client.actor.return_value = actor_mock
    dataset_mock = MagicMock()
    dataset_mock.iterate_items.return_value = iter(dataset_items or [])
    client.dataset.return_value = dataset_mock
    return client, actor_mock


def test_scrape_reels_nao_inclui_include_transcript_por_padrao():
    """Default False de propósito -- `includeTranscript` é cobrada por
    minuto de vídeo, e o piloto pequeno descrito na issue #88 precisa
    confirmar custo real antes de ligar para os 27 perfis."""
    client, actor_mock = _fake_client()
    scraper = InstagramScraper(client)

    scraper.scrape_reels(["governador_teste"])

    run_input = actor_mock.call.call_args.kwargs["run_input"]
    assert "includeTranscript" not in run_input


def test_scrape_reels_inclui_include_transcript_quando_habilitado_na_config():
    client, actor_mock = _fake_client()
    scraper = InstagramScraper(client, ScraperConfig(include_transcript=True))

    scraper.scrape_reels(["governador_teste"])

    run_input = actor_mock.call.call_args.kwargs["run_input"]
    assert run_input["includeTranscript"] is True


def test_scrape_reels_extra_run_input_sobrescreve_include_transcript():
    """Mesmo padrão de `resultsLimit`: `extra_run_input` tem a última
    palavra sobre qualquer chave do `run_input`, incluindo `includeTranscript`."""
    client, actor_mock = _fake_client()
    scraper = InstagramScraper(client, ScraperConfig(include_transcript=True))

    scraper.scrape_reels(["governador_teste"], extra_run_input={"includeTranscript": False})

    run_input = actor_mock.call.call_args.kwargs["run_input"]
    assert run_input["includeTranscript"] is False


def test_scrape_reels_repassa_resultado_do_dataset():
    items = [{"id": "r1", "transcript": "fala do governador"}]
    client, _actor_mock = _fake_client(items)
    scraper = InstagramScraper(client, ScraperConfig(include_transcript=True))

    resultado = scraper.scrape_reels(["governador_teste"])

    assert resultado == items
