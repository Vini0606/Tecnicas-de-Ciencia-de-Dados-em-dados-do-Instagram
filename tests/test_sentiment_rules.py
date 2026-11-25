import pandas as pd
import pytest

from src.modeling.sentiment_rules import (
    COLUNA_ROTULO_MODELO,
    apply_codigo_de_campanha,
    is_codigo_de_campanha,
)


@pytest.mark.parametrize(
    "texto",
    [
        "5️⃣5️⃣💙🚀",
        "4️⃣0️⃣0️⃣✅",
        "🚀🚀🚀",
        "13 ❤️",
        "Elmano 1️⃣3️⃣🚀",
        "Vote 44 🚀🚀",
    ],
)
def test_reconhece_apoio_em_codigo_de_campanha(texto):
    assert is_codigo_de_campanha(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "22",  # número sem emoji de apoio: pode ser apoio ou provocação
        "13 13",
        "1️⃣3️⃣🤮🤮",  # emoji de reprovação
        "13 ❤️ 🤡",
        "Parabéns governador ❤️",  # texto com apoio, sem número: fica com o modelo
        "😂😂😂",
        "Em 2022 prometeu a estrada e até hoje nada, mas seguimos esperando 🙏",  # texto longo
        "",
        None,
    ],
)
def test_nao_reconhece_o_que_nao_e_codigo_de_campanha(texto):
    assert not is_codigo_de_campanha(texto)


def test_so_promove_neutral_e_guarda_o_rotulo_do_modelo():
    df = pd.DataFrame(
        {
            "text": ["5️⃣5️⃣💙", "5️⃣5️⃣💙", "5️⃣5️⃣💙", "bom dia", "5️⃣5️⃣💙"],
            "sentiment_label": ["neutral", "negative", "positive", "neutral", None],
        }
    )

    resultado = apply_codigo_de_campanha(df)

    assert list(resultado["sentiment_label"][:4]) == ["positive", "negative", "positive", "neutral"]
    assert pd.isna(resultado["sentiment_label"][4])
    assert list(resultado[COLUNA_ROTULO_MODELO][:4]) == ["neutral", "negative", "positive", "neutral"]
    assert list(df["sentiment_label"][:4]) == ["neutral", "negative", "positive", "neutral"]


def test_reaplicar_parte_do_rotulo_do_modelo():
    df = pd.DataFrame({"text": ["5️⃣5️⃣💙", "22"], "sentiment_label": ["neutral", "neutral"]})

    uma_vez = apply_codigo_de_campanha(df)
    duas_vezes = apply_codigo_de_campanha(uma_vez)

    pd.testing.assert_frame_equal(uma_vez, duas_vezes)
