from unittest.mock import MagicMock

import pytest


def test_run_falha_sem_api_gemini(monkeypatch):
    import scripts.refine_topics as refine_topics_script

    monkeypatch.delenv("API_GEMINI", raising=False)
    monkeypatch.setattr(
        "scripts.refine_topics.load_checkpoint", lambda run_id: MagicMock()
    )

    with pytest.raises(ValueError, match="API_GEMINI"):
        refine_topics_script.run(run_id="run_abc")


def test_run_refina_e_resalva_checkpoint_no_run_id_original(monkeypatch):
    import scripts.refine_topics as refine_topics_script

    monkeypatch.setenv("API_GEMINI", "fake-key")

    fake_checkpoint = MagicMock(
        topic_model="topic_model_original",
        docs=["doc1"],
        df_comments="df_comments_original",
        df_reels="df_reels_x",
        pca_model="pca_x",
        pca_feature_columns=["a"],
        cluster_model="cluster_x",
        cluster_config={},
        cluster_score=0.1,
        cluster_algo_name="KMeans",
        embedding_model_name="modelo-fake",
    )
    monkeypatch.setattr(
        "scripts.refine_topics.load_checkpoint", lambda run_id: fake_checkpoint
    )

    fake_refinement = MagicMock(
        topic_model="topic_model_refinado",
        df_comments="df_comments_refinado",
        run_id="run_refinamento",
    )
    fake_refine = MagicMock(return_value=fake_refinement)
    monkeypatch.setattr("scripts.refine_topics.refine_topics_with_gemini", fake_refine)

    fake_save_checkpoint = MagicMock()
    monkeypatch.setattr("scripts.refine_topics.save_checkpoint", fake_save_checkpoint)

    result_run_id = refine_topics_script.run(run_id="run_original")

    assert result_run_id == "run_refinamento"

    fake_refine.assert_called_once()
    call_args = fake_refine.call_args
    assert call_args.args[0] == "topic_model_original"
    assert call_args.args[1] == ["doc1"]
    assert call_args.args[2] == "df_comments_original"
    assert call_args.args[3].api_key == "fake-key"

    fake_save_checkpoint.assert_called_once()
    assert fake_save_checkpoint.call_args.args[0] == "run_original"
    save_kwargs = fake_save_checkpoint.call_args.kwargs
    assert save_kwargs["topic_model"] == "topic_model_refinado"
    assert save_kwargs["df_comments"] == "df_comments_refinado"
    assert save_kwargs["df_reels"] == "df_reels_x"
    assert save_kwargs["pca_model"] == "pca_x"
    assert save_kwargs["cluster_algo_name"] == "KMeans"
    assert save_kwargs["embedding_model_name"] == "modelo-fake"
