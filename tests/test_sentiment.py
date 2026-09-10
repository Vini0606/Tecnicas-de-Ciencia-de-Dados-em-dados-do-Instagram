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


def test_analyze_sentiment_com_texto_longo_e_formal_nao_quebra():
    """ADR 0020 (Ficha 3) / issue #88, user story 4: legenda/transcrição são
    texto mais longo e formal (fala de assessoria) do que o comentário curto
    e informal em que o `cardiffnlp/twitter-xlm-roberta-base-sentiment`
    (`SentimentConfig.model_name`) foi treinado -- ver limitação documentada
    em `SentimentConfig`. Este teste cobre só que o pipeline não quebra com
    um texto bem mais longo que um comentário típico (a truncagem
    `truncation=True, max_length=512` já existente em `analyze_sentiment`
    é o mecanismo que evita isso); a qualidade do rótulo em texto formal
    real não é validada aqui -- é a limitação de modelo que a issue pede
    para documentar, não resolver nesta rodada."""
    texto_formal_longo = (
        "Nesta manhã, tivemos a honra de inaugurar mais uma unidade de saúde "
        "que vai atender milhares de famílias em toda a região metropolitana. "
        "Este é um marco importante da nossa gestão, fruto de meses de "
        "planejamento em conjunto com as secretarias municipais e estaduais, "
        "e reforça nosso compromisso histórico com a ampliação do acesso à "
        "saúde pública de qualidade para toda a população do nosso estado. "
    ) * 5  # bem mais longo que um comentário típico de rede social
    df_textos = pd.DataFrame({"text": [texto_formal_longo]})
    config = SentimentConfig(text_column="text")
    textos_recebidos = []

    def pipeline_espiao(texto, **kwargs):
        textos_recebidos.append((texto, kwargs))
        return [{"label": "Positive", "score": 0.6}]

    df_out = analyze_sentiment(df_textos, config, sentiment_pipeline=pipeline_espiao)

    assert df_out.loc[0, "sentiment_label"] == "Positive"
    assert not df_out["sentiment_label"].isna().any()
    # A mesma chamada de truncagem usada para comentários curtos também
    # protege o texto formal/longo -- nenhum tratamento especial extra por
    # fonte é necessário para não quebrar.
    _texto_chamado, kwargs_chamados = textos_recebidos[0]
    assert kwargs_chamados == {"truncation": True, "max_length": 512}
