import pandas as pd

from src.modeling.config import SentimentConfig
from src.modeling.sentiment import analyze_sentiment


def _fake_pipeline(texto, **kwargs):
    if "ótimo" in texto:
        return [{"label": "Positive", "score": 0.99}]
    return [{"label": "Negative", "score": 0.87}]


def test_analyze_sentiment_usa_pipeline_injetado_sem_baixar_modelo():
    df_comments = pd.DataFrame({"text": ["trabalho ótimo", "isso é péssimo"]})
    config = SentimentConfig(text_column="text")

    df_out = analyze_sentiment(df_comments, config, sentiment_pipeline=_fake_pipeline)

    assert list(df_out["sentiment_label"]) == ["Positive", "Negative"]
    assert list(df_out["sentiment_score"]) == [0.99, 0.87]


def test_analyze_sentiment_com_texto_vazio_ou_nulo_retorna_none():
    df_comments = pd.DataFrame({"text": ["", None, "  "]})
    config = SentimentConfig(text_column="text")

    df_out = analyze_sentiment(df_comments, config, sentiment_pipeline=_fake_pipeline)

    assert df_out["sentiment_label"].isna().all()
    assert df_out["sentiment_score"].isna().all()


def test_analyze_sentiment_com_falha_no_pipeline_retorna_none():
    def pipeline_com_erro(texto, **kwargs):
        raise RuntimeError("falha simulada")

    df_comments = pd.DataFrame({"text": ["qualquer texto"]})
    config = SentimentConfig(text_column="text")

    df_out = analyze_sentiment(df_comments, config, sentiment_pipeline=pipeline_com_erro)

    assert df_out["sentiment_label"].isna().all()
