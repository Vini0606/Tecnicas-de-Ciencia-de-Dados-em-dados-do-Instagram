from unittest.mock import MagicMock

import pandas as pd
import pytest


def _fake_bronze_writer_class(df_profiles, df_posts, df_reels):
    class FakeBronzeWriter:
        def __init__(self, **kwargs):
            pass

        def get_latest_profiles(self):
            return df_profiles

        def get_latest_posts(self):
            return df_posts

        def get_latest_reels(self):
            return df_reels

        def write_profiles(self, *a, **k):
            pass

        def write_posts(self, *a, **k):
            pass

        def write_reels(self, *a, **k):
            pass

    return FakeBronzeWriter


def _patch_medallion_dependencies(monkeypatch, df_reels_silver, df_comments_silver):
    df_profiles = pd.DataFrame({"id": ["1"]})
    df_posts = pd.DataFrame({"id": ["1"]})
    df_reels = pd.DataFrame({"id": ["1"]})

    monkeypatch.setattr(
        "pipeline.BronzeWriter", _fake_bronze_writer_class(df_profiles, df_posts, df_reels)
    )

    profile_cleaner = MagicMock()
    profile_cleaner.clean.return_value = pd.DataFrame({"id": ["1"]})
    post_cleaner = MagicMock()
    post_cleaner.clean_posts.return_value = pd.DataFrame({"id": ["1"]})
    post_cleaner.clean_reels.return_value = df_reels_silver
    comment_cleaner = MagicMock()
    comment_cleaner.clean.return_value = df_comments_silver
    aggregator = MagicMock()
    aggregator.aggregate.return_value = pd.DataFrame({"id": ["1"]})

    governors_cleaner = MagicMock()
    governors_cleaner.clean.return_value = pd.DataFrame({"inputUrl": ["u1"]})

    monkeypatch.setattr("pipeline.ProfileCleaner", lambda: profile_cleaner)
    monkeypatch.setattr("pipeline.PostCleaner", lambda: post_cleaner)
    monkeypatch.setattr("pipeline.CommentCleaner", lambda: comment_cleaner)
    monkeypatch.setattr("pipeline.EngagementAggregator", lambda: aggregator)
    monkeypatch.setattr("pipeline.GovernorsMetadataCleaner", lambda: governors_cleaner)
    monkeypatch.setattr(
        "pipeline.pd.read_excel", lambda *a, **k: pd.DataFrame({"Link": ["u1"]})
    )

    fake_run_deterministic_modeling = MagicMock()
    monkeypatch.setattr("pipeline.run_deterministic_modeling", fake_run_deterministic_modeling)
    return fake_run_deterministic_modeling, aggregator


def test_run_medallion_pipeline_nao_roda_modelagem_por_padrao(monkeypatch):
    import pipeline

    df_reels_silver = pd.DataFrame({"id": ["1"]})
    df_comments_silver = pd.DataFrame({"text": ["oi"]})
    fake_modeling, _aggregator = _patch_medallion_dependencies(
        monkeypatch, df_reels_silver, df_comments_silver
    )

    pipeline.run_medallion_pipeline(apify_api_token="token", links=["l"], run_id="r1")

    fake_modeling.assert_not_called()


def test_run_medallion_pipeline_com_run_modeling_chama_estagio_deterministico(monkeypatch):
    import pipeline

    df_reels_silver = pd.DataFrame({"id": ["1"]})
    df_comments_silver = pd.DataFrame({"text": ["oi"]})
    fake_modeling, aggregator = _patch_medallion_dependencies(
        monkeypatch, df_reels_silver, df_comments_silver
    )

    pipeline.run_medallion_pipeline(
        apify_api_token="token", links=["l"], run_id="r1", run_modeling=True
    )

    fake_modeling.assert_called_once()
    args, kwargs = fake_modeling.call_args
    assert args[0] is df_reels_silver
    assert args[1] is df_comments_silver
    # ADR 0019 (parte C): o novo passo [PERFORMANCE-POR-POST] precisa de
    # df_posts_silver e do df_gold (governor_engagement) já calculados aqui.
    # `pipeline.PostCleaner()` devolve o mesmo mock usado internamente (ver
    # `_patch_medallion_dependencies`).
    assert args[2] is pipeline.PostCleaner().clean_posts.return_value
    assert args[3] is aggregator.aggregate.return_value
    # ADR 0001: "um run_id = um estado imutável" -- a modelagem deve gerar o
    # seu próprio run_id, nunca reaproveitar o run_id da ingestão.
    assert kwargs.get("run_id") != "r1"


def test_run_medallion_pipeline_grava_tabela_de_historico_em_append(monkeypatch):
    """ADR 0016: além da tabela `governor_engagement` (overwrite, como
    sempre), o pipeline agora também grava `governor_engagement_history`
    em modo append -- sem isso não há como acumular tendência ao longo do
    tempo."""
    import pipeline
    from config import settings

    df_reels_silver = pd.DataFrame({"id": ["1"]})
    df_comments_silver = pd.DataFrame({"text": ["oi"]})
    _fake_modeling, aggregator = _patch_medallion_dependencies(
        monkeypatch, df_reels_silver, df_comments_silver
    )

    pipeline.run_medallion_pipeline(apify_api_token="token", links=["l"], run_id="r1")

    assert aggregator.write.call_count == 2
    first_call, second_call = aggregator.write.call_args_list
    assert first_call.args[1] == settings.GOLD_ENGAGEMENT
    assert second_call.args[1] == settings.GOLD_ENGAGEMENT_HISTORY
    assert second_call.kwargs.get("mode") == "append"


def test_run_medallion_pipeline_nunca_chama_refinamento_via_gemini(monkeypatch):
    """O refinamento via Gemini é sempre manual (ver ADR 0001) -- não deve
    existir nenhum caminho em pipeline.py que o dispare automaticamente."""
    import pipeline

    assert not hasattr(pipeline, "refine_topics_with_gemini")


def _fake_bronze_writer_class_recording(calls):
    df_profiles = pd.DataFrame({"id": ["1"]})
    df_posts = pd.DataFrame({"id": ["1"]})
    df_reels = pd.DataFrame({"id": ["1"]})

    class FakeBronzeWriter:
        def __init__(self, **kwargs):
            pass

        def get_latest_profiles(self):
            return df_profiles

        def get_latest_posts(self):
            return df_posts

        def get_latest_reels(self):
            return df_reels

        def write_profiles(self, raw_data, run_id=None):
            calls.append(("profiles", raw_data, run_id))

        def write_posts(self, raw_data, run_id=None):
            calls.append(("posts", raw_data, run_id))

        def write_reels(self, raw_data, run_id=None):
            calls.append(("reels", raw_data, run_id))

    return FakeBronzeWriter


def test_run_medallion_pipeline_branch_de_extracao_usa_extract_and_land(
    monkeypatch, tmp_path
):
    """force_extract=True (sem Bronze/JSON local) deve raspar via
    extract_and_land -- que arquiva na landing zone antes de escrever na
    Bronze (ver ADR 0011)."""
    import pipeline

    df_reels_silver = pd.DataFrame({"id": ["1"]})
    df_comments_silver = pd.DataFrame({"text": ["oi"]})
    _patch_medallion_dependencies(monkeypatch, df_reels_silver, df_comments_silver)

    bronze_calls = []
    monkeypatch.setattr(
        "pipeline.BronzeWriter", _fake_bronze_writer_class_recording(bronze_calls)
    )

    fake_scraper = MagicMock()
    fake_scraper.scrape_profiles.return_value = [{"inputUrl": "u1", "username": "gov1"}]
    fake_scraper.scrape_posts.return_value = [{"inputUrl": "u1", "id": "p1"}]
    fake_scraper.scrape_reels.return_value = [{"inputUrl": "u1", "id": "r1"}]
    monkeypatch.setattr("pipeline.ApifyClient", lambda token: MagicMock())
    monkeypatch.setattr(
        "pipeline.InstagramScraper", lambda client, config: fake_scraper
    )
    monkeypatch.setattr("pipeline.settings.LANDING_DIR", tmp_path / "landing")

    pipeline.run_medallion_pipeline(
        apify_api_token="token", links=["u1"], run_id="run_extract", force_extract=True
    )

    assert {kind for kind, _, _ in bronze_calls} == {"profiles", "posts", "reels"}
    assert all(run_id == "run_extract" for _, _, run_id in bronze_calls)
    assert (tmp_path / "landing" / "run_extract" / "profiles.json").exists()
    assert (tmp_path / "landing" / "run_extract" / "posts.json").exists()
    assert (tmp_path / "landing" / "run_extract" / "reels.json").exists()


def _setup_extraction_branch(monkeypatch, tmp_path):
    """Configura o pipeline para tomar o branch de extracao real (sem
    depender de cache), reaproveitando os mocks das outras etapas."""
    df_reels_silver = pd.DataFrame({"id": ["1"]})
    df_comments_silver = pd.DataFrame({"text": ["oi"]})
    _patch_medallion_dependencies(monkeypatch, df_reels_silver, df_comments_silver)

    bronze_calls = []
    monkeypatch.setattr(
        "pipeline.BronzeWriter", _fake_bronze_writer_class_recording(bronze_calls)
    )

    fake_scraper = MagicMock()
    fake_scraper.scrape_profiles.return_value = [{"inputUrl": "u1", "username": "gov1"}]
    fake_scraper.scrape_posts.return_value = [{"inputUrl": "u1", "id": "p1"}]
    fake_scraper.scrape_reels.return_value = [{"inputUrl": "u1", "id": "r1"}]
    monkeypatch.setattr("pipeline.ApifyClient", lambda token: MagicMock())
    monkeypatch.setattr(
        "pipeline.InstagramScraper", lambda client, config: fake_scraper
    )
    monkeypatch.setattr("pipeline.settings.LANDING_DIR", tmp_path / "landing")
    return bronze_calls


def test_confirm_extraction_recusada_aborta_sem_extrair(monkeypatch, tmp_path):
    """Issue #35: sem cache local, run_medallion_pipeline nao deve disparar
    uma extracao real sem antes checar confirm_extraction."""
    import pipeline

    bronze_calls = _setup_extraction_branch(monkeypatch, tmp_path)

    with pytest.raises(SystemExit):
        pipeline.run_medallion_pipeline(
            apify_api_token="token",
            links=["u1"],
            run_id="run_extract",
            force_extract=True,
            confirm_extraction=lambda estimated_cost: False,
        )

    assert bronze_calls == []


def test_confirm_extraction_aceita_prossegue_com_extracao(monkeypatch, tmp_path):
    import pipeline

    bronze_calls = _setup_extraction_branch(monkeypatch, tmp_path)

    pipeline.run_medallion_pipeline(
        apify_api_token="token",
        links=["u1"],
        run_id="run_extract",
        force_extract=True,
        confirm_extraction=lambda estimated_cost: True,
    )

    assert {kind for kind, _, _ in bronze_calls} == {"profiles", "posts", "reels"}


def test_confirm_extraction_recebe_estimativa_baseada_em_results_limit(monkeypatch, tmp_path):
    import pipeline
    from scripts.apify_backfill_shared import estimate_cost_usd_for_results_limit

    _setup_extraction_branch(monkeypatch, tmp_path)
    custos_recebidos = []

    def _confirm(estimated_cost):
        custos_recebidos.append(estimated_cost)
        return True

    pipeline.run_medallion_pipeline(
        apify_api_token="token",
        links=["u1"],
        results_limit=50,
        run_id="run_extract",
        force_extract=True,
        confirm_extraction=_confirm,
    )

    assert custos_recebidos == [estimate_cost_usd_for_results_limit(50, n_governors=1)]


def test_confirm_extraction_nao_e_chamada_quando_bronze_ja_tem_dado(monkeypatch):
    """O gate so faz sentido quando uma extracao real vai de fato acontecer
    -- com a Bronze em cache, run_medallion_pipeline nunca deveria nem
    avaliar o custo."""
    import pipeline

    df_reels_silver = pd.DataFrame({"id": ["1"]})
    df_comments_silver = pd.DataFrame({"text": ["oi"]})
    _patch_medallion_dependencies(monkeypatch, df_reels_silver, df_comments_silver)

    confirm_extraction = MagicMock()

    pipeline.run_medallion_pipeline(
        apify_api_token="token",
        links=["l"],
        run_id="r1",
        confirm_extraction=confirm_extraction,
    )

    confirm_extraction.assert_not_called()
