import pandas as pd
import pytest

from src.analysis.medallion_diagnostics import (
    completeness_summary,
    count_duplicate_rows,
    with_governor_metadata,
)


def _df_com_nulos():
    return pd.DataFrame(
        {
            "a": [1, 2, None, 4],
            "b": ["x", "x", "y", None],
        }
    )


def test_completeness_summary_conta_nulos_e_percentual_por_coluna():
    resultado = completeness_summary(_df_com_nulos())
    linha_a = resultado.set_index("coluna").loc["a"]
    linha_b = resultado.set_index("coluna").loc["b"]

    assert linha_a["n_nulos"] == 1
    assert linha_a["pct_nulos"] == pytest.approx(25.0)
    assert linha_b["n_nulos"] == 1
    assert linha_b["pct_nulos"] == pytest.approx(25.0)


def test_completeness_summary_conta_valores_unicos_ignorando_nulos():
    resultado = completeness_summary(_df_com_nulos())
    linha_b = resultado.set_index("coluna").loc["b"]

    # "x", "x", "y", None -> 2 valores únicos não-nulos, não 3.
    assert linha_b["n_unicos"] == 2


def test_completeness_summary_dataframe_vazio_nao_levanta_erro():
    df_vazio = pd.DataFrame({"a": pd.Series(dtype="float64")})
    resultado = completeness_summary(df_vazio)

    assert resultado.set_index("coluna").loc["a", "n_nulos"] == 0
    assert resultado.set_index("coluna").loc["a", "pct_nulos"] == 0.0


def test_completeness_summary_uma_linha_por_coluna_na_ordem_original():
    resultado = completeness_summary(_df_com_nulos())
    assert list(resultado["coluna"]) == ["a", "b"]


def test_count_duplicate_rows_sem_subset_conta_linhas_inteiras_repetidas():
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    assert count_duplicate_rows(df) == 1


def test_count_duplicate_rows_com_subset_ignora_outras_colunas():
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "z", "y"]})
    # "a" repete em duas linhas mesmo com "b" diferente -- subset restringe a
    # checagem de duplicidade só a "a".
    assert count_duplicate_rows(df, subset=["a"]) == 1
    assert count_duplicate_rows(df) == 0


def _df_governors_metadata():
    return pd.DataFrame(
        {
            "inputUrl": ["https://instagram.com/gov_a/", "https://instagram.com/gov_b/"],
            "nome": ["Governador A", "Governador B"],
            "uf": ["SP", "RJ"],
            "partido": ["PARTIDO_X", "PARTIDO_Y"],
        }
    )


def test_with_governor_metadata_traz_partido_e_uf_por_inputurl():
    df_gold = pd.DataFrame(
        {"inputUrl": ["https://instagram.com/gov_a/"], "nsm": [0.5]}
    )
    resultado = with_governor_metadata(df_gold, _df_governors_metadata())

    assert resultado.loc[0, "uf"] == "SP"
    assert resultado.loc[0, "partido"] == "PARTIDO_X"


def test_with_governor_metadata_left_join_preserva_linhas_sem_metadado():
    df_gold = pd.DataFrame(
        {"inputUrl": ["https://instagram.com/gov_desconhecido/"], "nsm": [0.1]}
    )
    resultado = with_governor_metadata(df_gold, _df_governors_metadata())

    assert len(resultado) == 1
    assert pd.isna(resultado.loc[0, "partido"])


def test_with_governor_metadata_levanta_erro_sem_coluna_inputurl():
    df_sem_chave = pd.DataFrame({"username": ["gov_a"], "nsm": [0.5]})

    with pytest.raises(ValueError, match="inputUrl"):
        with_governor_metadata(df_sem_chave, _df_governors_metadata())
