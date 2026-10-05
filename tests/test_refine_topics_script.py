from unittest.mock import MagicMock

import pytest


def _checkpoint(with_discourse=True):
    return MagicMock(
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
        discourse_topic_model="discurso_original" if with_discourse else None,
        docs_discourse=["legenda1"],
        df_discourse="df_discurso_original",
        discourse_embedding_model_name="modelo-discurso",
    )


def _patch_script(monkeypatch, checkpoint):
    import scripts.refine_topics as script

    monkeypatch.setenv("API_GEMINI", "fake-key")
    monkeypatch.setattr(script, "load_checkpoint", lambda run_id: checkpoint)
    fake_comments = MagicMock(
        return_value=MagicMock(
            topic_model="topic_model_refinado",
            df_comments="df_comments_refinado",
            run_id="run_refinamento",
        )
    )
    fake_discourse = MagicMock(
        return_value=MagicMock(
            topic_model="discurso_refinado",
            df_discourse="df_discurso_refinado",
            run_id="run_refinamento",
        )
    )
    fake_save = MagicMock()
    monkeypatch.setattr(script, "refine_topics_with_gemini", fake_comments)
    monkeypatch.setattr(script, "refine_discourse_topics_with_gemini", fake_discourse)
    monkeypatch.setattr(script, "save_checkpoint", fake_save)
    return script, fake_comments, fake_discourse, fake_save


def test_run_falha_sem_api_gemini(monkeypatch):
    import scripts.refine_topics as refine_topics_script

    monkeypatch.delenv("API_GEMINI", raising=False)
    monkeypatch.setattr(
        "scripts.refine_topics.load_checkpoint", lambda run_id: MagicMock()
    )

    with pytest.raises(ValueError, match="API_GEMINI"):
        refine_topics_script.run(run_id="run_abc")


def test_run_padrao_refina_comentario_e_discurso_e_resalva_checkpoint(monkeypatch):
    script, fake_comments, fake_discourse, fake_save = _patch_script(
        monkeypatch, _checkpoint()
    )

    result_run_id = script.run(run_id="run_original")

    assert result_run_id == "run_refinamento"

    fake_comments.assert_called_once()
    call_args = fake_comments.call_args
    assert call_args.args[0] == "topic_model_original"
    assert call_args.args[1] == ["doc1"]
    assert call_args.args[2] == "df_comments_original"
    assert call_args.args[3].api_key == "fake-key"

    fake_discourse.assert_called_once()
    d_args = fake_discourse.call_args
    assert d_args.args[:3] == (
        "discurso_original",
        ["legenda1"],
        "df_discurso_original",
    )
    # mesmo run_id do refino de comentarios
    assert d_args.kwargs["run_id"] == "run_refinamento"

    fake_save.assert_called_once()
    assert fake_save.call_args.args[0] == "run_original"
    save_kwargs = fake_save.call_args.kwargs
    assert save_kwargs["topic_model"] == "topic_model_refinado"
    assert save_kwargs["df_comments"] == "df_comments_refinado"
    assert save_kwargs["discourse_topic_model"] == "discurso_refinado"
    assert save_kwargs["df_discourse"] == "df_discurso_refinado"
    assert save_kwargs["df_reels"] == "df_reels_x"
    assert save_kwargs["pca_model"] == "pca_x"
    assert save_kwargs["cluster_algo_name"] == "KMeans"
    assert save_kwargs["embedding_model_name"] == "modelo-fake"
    assert save_kwargs["discourse_embedding_model_name"] == "modelo-discurso"


def test_target_comments_nao_toca_no_discurso(monkeypatch):
    script, fake_comments, fake_discourse, fake_save = _patch_script(
        monkeypatch, _checkpoint()
    )

    script.run(run_id="run_original", target="comments")

    fake_comments.assert_called_once()
    fake_discourse.assert_not_called()
    assert fake_save.call_args.kwargs["discourse_topic_model"] == "discurso_original"


def test_target_discourse_nao_toca_nos_comentarios(monkeypatch):
    script, fake_comments, fake_discourse, fake_save = _patch_script(
        monkeypatch, _checkpoint()
    )

    result_run_id = script.run(run_id="run_original", target="discourse")

    fake_comments.assert_not_called()
    fake_discourse.assert_called_once()
    assert fake_discourse.call_args.kwargs["run_id"] is None
    assert result_run_id == "run_refinamento"
    assert fake_save.call_args.kwargs["topic_model"] == "topic_model_original"


def test_checkpoint_sem_discurso_pula_no_alvo_padrao(monkeypatch):
    script, fake_comments, fake_discourse, _fake_save = _patch_script(
        monkeypatch, _checkpoint(with_discourse=False)
    )

    script.run(run_id="run_original")

    fake_comments.assert_called_once()
    fake_discourse.assert_not_called()


def test_checkpoint_sem_discurso_falha_com_mensagem_clara_no_alvo_discourse(
    monkeypatch,
):
    script, _c, fake_discourse, fake_save = _patch_script(
        monkeypatch, _checkpoint(with_discourse=False)
    )

    with pytest.raises(ValueError, match="modelo de topicos de discurso"):
        script.run(run_id="run_original", target="discourse")

    fake_discourse.assert_not_called()
    fake_save.assert_not_called()
