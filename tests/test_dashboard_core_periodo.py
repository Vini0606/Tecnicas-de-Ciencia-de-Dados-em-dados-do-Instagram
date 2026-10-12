import datetime

import pandas as pd

from dashboard.core.periodo import (
    ajustar_intervalo,
    excluir_fixados,
    filtrar_publicacoes,
    limites_de_datas,
    parse_intervalo_digitado,
)

D = datetime.date


def _df_publicacoes():
    return pd.DataFrame(
        {
            "id": ["a", "b", "c", "d"],
            "data_hora": pd.to_datetime(
                [
                    "2026-08-01 10:00",
                    "2026-08-10 23:59",
                    "2026-08-20 00:00",
                    "2026-09-01 12:00",
                ]
            ),
            "isPinned": [False, True, None, False],
        }
    )


# ---------------------------------------------------------------------------
# excluir_fixados -- regra: nulo (ou coluna ausente) = NAO fixado
# ---------------------------------------------------------------------------


def test_excluir_fixados_remove_so_o_verdadeiro():
    resultado = excluir_fixados(_df_publicacoes())
    assert resultado["id"].tolist() == ["a", "c", "d"]


def test_excluir_fixados_nulo_conta_como_nao_fixado():
    df = pd.DataFrame({"id": ["x"], "isPinned": [None]})
    assert excluir_fixados(df)["id"].tolist() == ["x"]


def test_excluir_fixados_sem_coluna_mantem_tudo():
    df = _df_publicacoes().drop(columns=["isPinned"])
    assert len(excluir_fixados(df)) == 4


def test_excluir_fixados_dataframe_vazio():
    assert excluir_fixados(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# limites_de_datas -- menor e maior dia COM dado (fixados nao contam)
# ---------------------------------------------------------------------------


def test_limites_ignoram_fixados():
    df = _df_publicacoes()
    df.loc[0, "isPinned"] = True  # 01/08 e 10/08 ficam fixados
    assert limites_de_datas(df, "data_hora") == (D(2026, 8, 20), D(2026, 9, 1))


def test_limites_sem_dado_retorna_none():
    assert limites_de_datas(pd.DataFrame(columns=["data_hora"]), "data_hora") is None
    assert limites_de_datas(pd.DataFrame(), "data_hora") is None


def test_limites_com_data_invalida_ignora_nat():
    df = pd.DataFrame({"data_hora": ["2026-08-05", "lixo"]})
    assert limites_de_datas(df, "data_hora") == (D(2026, 8, 5), D(2026, 8, 5))


# ---------------------------------------------------------------------------
# filtrar_publicacoes
# ---------------------------------------------------------------------------


def test_filtrar_dentro_do_intervalo_e_inclusivo_nas_pontas():
    resultado = filtrar_publicacoes(
        _df_publicacoes(), "data_hora", D(2026, 8, 1), D(2026, 8, 20)
    )
    assert resultado["id"].tolist() == ["a", "c"]  # b e fixado


def test_filtrar_considera_o_dia_inteiro_do_fim():
    df = _df_publicacoes()
    df["isPinned"] = False
    resultado = filtrar_publicacoes(df, "data_hora", D(2026, 8, 10), D(2026, 8, 10))
    assert resultado["id"].tolist() == ["b"]  # 23:59 do dia 10 entra


def test_filtrar_sem_limites_devolve_tudo_menos_fixados():
    resultado = filtrar_publicacoes(_df_publicacoes(), "data_hora", None, None)
    assert resultado["id"].tolist() == ["a", "c", "d"]


def test_filtrar_pode_manter_fixados():
    resultado = filtrar_publicacoes(
        _df_publicacoes(), "data_hora", None, None, excluir_fixados_=False
    )
    assert len(resultado) == 4


def test_filtrar_periodo_sem_publicacoes_devolve_vazio_com_colunas():
    resultado = filtrar_publicacoes(
        _df_publicacoes(), "data_hora", D(2026, 1, 1), D(2026, 1, 2)
    )
    assert resultado.empty
    assert "id" in resultado.columns


def test_filtrar_serie_vazia():
    assert filtrar_publicacoes(pd.DataFrame(), "data_hora", None, None).empty


def test_filtrar_nao_muta_a_entrada():
    df = _df_publicacoes()
    filtrar_publicacoes(df, "data_hora", D(2026, 8, 1), D(2026, 8, 2))
    assert len(df) == 4 and "_data" not in df.columns


# ---------------------------------------------------------------------------
# ajustar_intervalo -- presa ao intervalo com dado
# ---------------------------------------------------------------------------

LIM = (D(2026, 8, 1), D(2026, 9, 1))


def test_ajustar_intervalo_dentro_dos_limites_fica_igual():
    assert ajustar_intervalo(D(2026, 8, 5), D(2026, 8, 9), LIM) == (
        D(2026, 8, 5),
        D(2026, 8, 9),
    )


def test_ajustar_intervalo_fora_dos_limites_e_preso():
    assert ajustar_intervalo(D(2026, 7, 1), D(2026, 12, 1), LIM) == LIM


def test_ajustar_intervalo_invertido_e_reordenado():
    assert ajustar_intervalo(D(2026, 8, 9), D(2026, 8, 5), LIM) == (
        D(2026, 8, 5),
        D(2026, 8, 9),
    )


def test_ajustar_intervalo_totalmente_fora_colapsa_na_borda():
    assert ajustar_intervalo(D(2026, 1, 1), D(2026, 1, 5), LIM) == (LIM[0], LIM[0])


# ---------------------------------------------------------------------------
# parse_intervalo_digitado -- "de DATA ate DATA"
# ---------------------------------------------------------------------------


def test_parse_intervalo_br():
    assert parse_intervalo_digitado("de 01/08/2026 até 15/08/2026") == (
        D(2026, 8, 1),
        D(2026, 8, 15),
    )


def test_parse_intervalo_iso_e_sem_acento():
    assert parse_intervalo_digitado("2026-08-01 ate 2026-08-15") == (
        D(2026, 8, 1),
        D(2026, 8, 15),
    )


def test_parse_intervalo_uma_data_so_vira_dia_unico():
    assert parse_intervalo_digitado("05/08/2026") == (D(2026, 8, 5), D(2026, 8, 5))


def test_parse_intervalo_invalido_devolve_none():
    assert parse_intervalo_digitado("") is None
    assert parse_intervalo_digitado("ontem até hoje") is None
    assert parse_intervalo_digitado("31/02/2026 até 01/03/2026") is None
