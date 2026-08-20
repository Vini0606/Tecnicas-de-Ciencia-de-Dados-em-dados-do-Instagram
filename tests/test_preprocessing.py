import pandas as pd

from src.modeling.config import PreprocessingConfig
from src.modeling.preprocessing import demojize_text, preprocess_comments, remove_stopwords


def test_remove_stopwords_remove_apenas_as_stopwords_informadas():
    stopwords = frozenset({"de", "o", "a"})
    assert remove_stopwords("o governador de fato", stopwords) == "governador fato"


def test_remove_stopwords_com_entrada_nao_string_retorna_vazio():
    assert remove_stopwords(None, frozenset()) == ""


def test_demojize_text_converte_emoji_em_descricao():
    resultado = demojize_text("bom trabalho \U0001F44F")
    assert ":" in resultado


def test_preprocess_comments_adiciona_colunas_esperadas():
    df_comments = pd.DataFrame({"text": ["O trabalho está ótimo \U0001F44F"]})
    config = PreprocessingConfig(text_column="text", stopwords_language="portuguese")

    df_out = preprocess_comments(df_comments, config)

    assert "text clean" in df_out.columns
    assert "text_demojized" in df_out.columns
    assert "o" not in df_out.loc[0, "text clean"].lower().split()
