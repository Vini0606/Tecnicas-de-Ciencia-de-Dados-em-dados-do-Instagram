from unittest.mock import MagicMock

import pandas as pd

from src.modeling.config import GeminiRefinerConfig
from src.modeling.gemini_refiner import GeminiDocsRefiner, apply_gemini_refinement


def _fake_generative_model(monkeypatch, label="Resumo gerado pelo Gemini"):
    fake_response = MagicMock()
    fake_response.text = label
    fake_model_instance = MagicMock()
    fake_model_instance.generate_content.return_value = fake_response

    monkeypatch.setattr(
        "src.modeling.gemini_refiner.genai.GenerativeModel",
        MagicMock(return_value=fake_model_instance),
    )
    monkeypatch.setattr("src.modeling.gemini_refiner.genai.configure", MagicMock())
    return fake_model_instance


def test_extract_topics_adiciona_rotulo_gerado_pelo_gemini(monkeypatch):
    _fake_generative_model(monkeypatch, label="Comentários sobre saúde pública")

    refiner = GeminiDocsRefiner(api_key="fake-key", sleep_every_n_topics=0)
    documents = pd.DataFrame(
        {"Topic": [0, 0, 1], "Document": ["doc a", "doc b", "doc c"]}
    )
    topics = {0: [("saude", 0.5)], 1: [("educacao", 0.4)]}

    updated = refiner.extract_topics(topic_model=None, documents=documents, c_tf_idf=None, topics=topics)

    assert updated[0][0] == ("Comentários sobre saúde pública", 1.0)
    assert updated[1][0] == ("Comentários sobre saúde pública", 1.0)


def test_extract_topics_preserva_topico_de_ruido_sem_chamar_gemini(monkeypatch):
    fake_model = _fake_generative_model(monkeypatch)

    refiner = GeminiDocsRefiner(api_key="fake-key", sleep_every_n_topics=0)
    documents = pd.DataFrame({"Topic": [-1], "Document": ["doc a"]})
    topics = {-1: [("ruido", 0.1)]}

    updated = refiner.extract_topics(topic_model=None, documents=documents, c_tf_idf=None, topics=topics)

    assert updated == topics
    fake_model.generate_content.assert_not_called()


def test_extract_topics_com_erro_na_api_mantem_keywords_originais(monkeypatch):
    monkeypatch.setattr(
        "src.modeling.gemini_refiner.genai.GenerativeModel",
        MagicMock(side_effect=RuntimeError("falha simulada")),
    )
    monkeypatch.setattr("src.modeling.gemini_refiner.genai.configure", MagicMock())

    refiner = GeminiDocsRefiner(api_key="fake-key", sleep_every_n_topics=0)
    documents = pd.DataFrame({"Topic": [0], "Document": ["doc a"]})
    topics = {0: [("saude", 0.5)]}

    updated = refiner.extract_topics(topic_model=None, documents=documents, c_tf_idf=None, topics=topics)

    assert updated == topics


def test_apply_gemini_refinement_chama_update_topics_no_topic_model(monkeypatch):
    _fake_generative_model(monkeypatch)

    fake_topic_model = MagicMock()
    config = GeminiRefinerConfig(api_key="fake-key", sleep_every_n_topics=0)

    resultado = apply_gemini_refinement(fake_topic_model, ["doc a", "doc b"], config)

    assert resultado is fake_topic_model
    fake_topic_model.update_topics.assert_called_once()
    call_args = fake_topic_model.update_topics.call_args
    assert call_args.args[0] == ["doc a", "doc b"]
    assert isinstance(call_args.kwargs["representation_model"], GeminiDocsRefiner)
