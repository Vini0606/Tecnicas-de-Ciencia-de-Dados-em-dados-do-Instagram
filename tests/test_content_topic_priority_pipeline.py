"""Issue #190: ICE por pauta roda na modelagem deterministica (provisorio) e
e recalculado ao final do refino de discurso (Gemini sempre mockado)."""

import pandas as pd
from deltalake import DeltaTable

from src.modeling.config import GeminiRefinerConfig
from src.modeling.orchestration import refine_discourse_topics_with_gemini
from tests.test_discourse_refinement import _discourse_fixture, _run_modeling


def test_modelagem_deterministica_grava_ice_de_pautas(monkeypatch, tmp_path):
    config, _result, _saved = _run_modeling(monkeypatch, tmp_path)

    out = DeltaTable(str(config.gold_content_topic_priority_score_path)).to_pandas()
    assert {"Topic", "Name", "score", "n_reels", "_run_id"} <= set(out.columns)
    assert len(out) > 0
    assert out["n_comentarios"].sum() == 3


def test_refino_de_discurso_recalcula_ice_de_pautas_com_rotulo_refinado(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "src.modeling.orchestration.apply_gemini_refinement",
        lambda topic_model, docs, config, prompt_template=None: topic_model,
    )
    topic_model, df = _discourse_fixture()
    comments = pd.DataFrame(
        {
            "id_reel": ["a", "b", "c", "d"],
            "id_comment": ["1", "2", "3", "4"],
            "fonte": "comentario",
            "likesCount": 1,
            "repliesCount": 0,
            "sentiment_label": "positive",
            "sentiment_score": 0.9,
            "Topic": 2,
            "Name": "2_x",
        }
    )
    config = GeminiRefinerConfig(
        api_key="fake-key",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_content_topic_priority_score_path=tmp_path / "content_topic_priority_score",
    )

    refinement = refine_discourse_topics_with_gemini(
        topic_model, df["text"].tolist(), df, config, run_id="run_refino", df_comments=comments
    )

    out = DeltaTable(str(config.gold_content_topic_priority_score_path)).to_pandas()
    assert (out["_run_id"] == refinement.run_id).all()
    by_topic = out.set_index("Topic")
    assert by_topic.loc[0, "Name"] == "Saude publica"
    assert by_topic.loc[0, "n_reels"] == 2
    assert by_topic.loc[1, "Name"] == "sem assunto definido"
    assert -1 not in by_topic.index
    assert by_topic.loc[0, "n_comentarios"] == 2


def test_refino_de_discurso_sem_comentarios_nao_grava_ice(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.modeling.orchestration.apply_gemini_refinement",
        lambda topic_model, docs, config, prompt_template=None: topic_model,
    )
    topic_model, df = _discourse_fixture()
    config = GeminiRefinerConfig(
        api_key="fake-key",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_content_topic_priority_score_path=tmp_path / "content_topic_priority_score",
    )

    refine_discourse_topics_with_gemini(topic_model, df["text"].tolist(), df, config)

    assert not (tmp_path / "content_topic_priority_score").exists()
