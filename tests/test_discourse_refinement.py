"""Issue #186: refino via Gemini dos topicos de discurso + correcao do
overwrite de `governor_sentiment` (Gemini sempre mockado)."""

from unittest.mock import MagicMock

import pandas as pd
from deltalake import DeltaTable

from src.modeling.config import ClusterConfig, GeminiRefinerConfig, ModelingConfig
from src.modeling.gemini_refiner import DEGENERATE_TOPIC_LABEL
from src.modeling.orchestration import (
    refine_discourse_topics_with_gemini,
    refine_topics_with_gemini,
    run_deterministic_modeling,
)
from tests.test_orchestration import (
    _df_comments,
    _df_engagement_placeholder,
    _df_posts_placeholder,
    _df_reels,
    _fake_analyze_sentiment,
    _fake_apply_gemini_refinement,
    _make_fake_model_topics,
    _patch_post_performance_fakes,
)


def _modeling_config(tmp_path):
    return ModelingConfig(
        cluster=ClusterConfig(max_evals_per_algo=10, random_state=42, max_n_clusters=5),
        gold_clusters_reels_path=tmp_path / "governor_clusters_reels",
        gold_clusters_posts_path=tmp_path / "governor_clusters_posts",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
        gold_nsm_path=tmp_path / "governor_nsm",
        gold_nsm_history_path=tmp_path / "governor_nsm_history",
        gold_post_performance_coefficients_path=tmp_path
        / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path
        / "post_performance_predictions",
        gold_profile_clusters_engagement_path=tmp_path
        / "governor_profile_clusters_engagement",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )


def _run_modeling(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.modeling.orchestration.analyze_sentiment", _fake_analyze_sentiment
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.model_topics",
        _make_fake_model_topics("0_provisorio", "0_refinado"),
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.apply_gemini_refinement",
        _fake_apply_gemini_refinement,
    )
    _patch_post_performance_fakes(monkeypatch)
    # BERTopic.save/load nao funcionam com MagicMock: o checkpoint em si e
    # testado em test_checkpoint_discourse.py.
    saved = {}
    monkeypatch.setattr(
        "src.modeling.orchestration.save_checkpoint",
        lambda run_id, **kwargs: saved.update(kwargs),
    )
    config = _modeling_config(tmp_path)
    result = run_deterministic_modeling(
        _df_reels(),
        _df_comments(),
        _df_posts_placeholder(),
        _df_engagement_placeholder(),
        config,
    )
    return config, result, saved


def test_modelagem_persiste_modelo_e_documentos_de_discurso_no_checkpoint(
    monkeypatch, tmp_path
):
    _config, _result, saved = _run_modeling(monkeypatch, tmp_path)

    assert saved["discourse_topic_model"] is not None
    df_discourse = saved["df_discourse"]
    assert {"id_reel", "text", "fonte", "Topic", "Name"} <= set(df_discourse.columns)
    assert len(df_discourse) == 12 + 12  # legendas (posts) + transcricoes (reels)


def _discourse_fixture():
    """Modelo de discurso falso com 3 grupos de topico: 0 (normal),
    1 (degenerado, sem palavra alguma, como o "1____" real) e -1 (ruido)."""
    df = pd.DataFrame(
        {
            "id_reel": ["a", "b", "c", "d"],
            "text": ["saude", "saude 2", "###", "ruido"],
            "inputUrl": "https://instagram.com/gov",
            "ownerUsername": "gov",
            "timestamp": "2026-01-01",
            "fonte": "legenda",
            "Topic": [0, 0, 1, -1],
            "Name": ["0_saude", "0_saude", "1____", "-1_x"],
        }
    )
    topic_model = MagicMock()
    topic_model.get_topics.return_value = {
        -1: [("x", 0.1)],
        0: [("saude", 0.5), ("hospital", 0.4)],
        1: [("", 0.0), ("", 0.0)],
    }
    topic_model.get_document_info.return_value = pd.DataFrame(
        {
            "Document": df["text"],
            "Topic": df["Topic"],
            # apos o refino do Gemini o BERTopic prefixa o rotulo gerado
            "Name": ["0_Saude publica", "0_Saude publica", "1_inventado", "-1_x"],
        }
    )
    return topic_model, df


def test_refino_de_discurso_grava_rotulos_novos_e_nao_refina_ruido(
    monkeypatch, tmp_path
):
    recorded = {}

    def _fake_apply(topic_model, docs, config, prompt_template=None):
        recorded["prompt_template"] = prompt_template
        return topic_model

    monkeypatch.setattr(
        "src.modeling.orchestration.apply_gemini_refinement", _fake_apply
    )
    topic_model, df = _discourse_fixture()
    config = GeminiRefinerConfig(
        api_key="fake-key",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
    )

    refinement = refine_discourse_topics_with_gemini(
        topic_model, df["text"].tolist(), df, config, run_id="run_refino"
    )

    out = (
        DeltaTable(str(config.gold_discourse_topics_path))
        .to_pandas()
        .set_index("id_reel")
    )
    assert (out["_run_id"] == "run_refino").all()
    assert refinement.run_id == "run_refino"
    assert out.loc["a", "Name"] == "0_Saude publica"
    # ruido (-1) nunca e tratado como tema: mantem o nome original
    assert out.loc["d", "Name"] == "-1_x"
    assert out.loc["d", "Topic"] == -1
    # o prompt usado e o de discurso (legendas), nao o de comentarios
    assert "legenda" in recorded["prompt_template"].lower()


def test_refino_de_discurso_rotula_topico_degenerado_explicitamente(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "src.modeling.orchestration.apply_gemini_refinement",
        lambda topic_model, docs, config, prompt_template=None: topic_model,
    )
    topic_model, df = _discourse_fixture()
    config = GeminiRefinerConfig(
        api_key="fake-key",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
    )

    refine_discourse_topics_with_gemini(topic_model, df["text"].tolist(), df, config)

    out = (
        DeltaTable(str(config.gold_discourse_topics_path))
        .to_pandas()
        .set_index("id_reel")
    )
    assert out.loc["c", "Name"] == DEGENERATE_TOPIC_LABEL == "sem assunto definido"


def test_refino_de_comentario_preserva_linhas_de_legenda_e_transcricao(
    monkeypatch, tmp_path
):
    """Regressao do overwrite (issue #186): refinar comentarios nao pode
    apagar as linhas legenda/transcricao de `governor_sentiment`."""
    config, result, _saved = _run_modeling(monkeypatch, tmp_path)
    before = DeltaTable(str(config.gold_sentiment_path)).to_pandas()
    n_legenda = (before["fonte"] == "legenda").sum()
    n_transcricao = (before["fonte"] == "transcricao").sum()
    assert n_legenda > 0 and n_transcricao > 0

    gemini_config = GeminiRefinerConfig(
        api_key="fake-key",
        gold_sentiment_path=config.gold_sentiment_path,
        gold_topic_priority_score_path=config.gold_topic_priority_score_path,
    )
    refinement = refine_topics_with_gemini(
        result.topic_model, result.docs, result.df_comments, gemini_config
    )

    after = DeltaTable(str(config.gold_sentiment_path)).to_pandas()
    assert (after["fonte"] == "legenda").sum() == n_legenda
    assert (after["fonte"] == "transcricao").sum() == n_transcricao
    comentarios = after[after["fonte"] == "comentario"]
    assert len(comentarios) == len(result.df_comments)
    assert (comentarios["_run_id"] == refinement.run_id).all()
    assert (comentarios["Name"] == "0_refinado").all()
    # Linhas preservadas mantem a procedencia original.
    assert (after[after["fonte"] != "comentario"]["_run_id"] == result.run_id).all()
