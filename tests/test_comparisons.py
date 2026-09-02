import numpy as np
import pandas as pd
import pytest

from src.dashboard.comparisons import compute_governor_comparison

METRICS = ["followersCount", "TOTAL ENGAJAMENTO", "% ENGAJAMENTO"]


def _df_engagement():
    return pd.DataFrame(
        {
            "inputUrl": [
                "https://www.instagram.com/governador_a/",
                "https://www.instagram.com/governador_b/",
                "https://www.instagram.com/governador_c/",
                "https://www.instagram.com/governador_d/",
            ],
            "followersCount": [1000, 2000, 3000, 4000],
            "TOTAL ENGAJAMENTO": [100, 300, 200, 400],
            "% ENGAJAMENTO": [1.0, 3.0, 2.0, 4.0],
        }
    )


def test_value_delta_e_rank_para_governador_no_meio_do_grupo():
    out = compute_governor_comparison(
        _df_engagement(), "https://www.instagram.com/governador_c/", METRICS
    )
    linha = out.set_index("metric").loc["TOTAL ENGAJAMENTO"]

    assert linha["value"] == 200
    # Média dos outros 3 (100, 300, 400) = 266.67, excluindo o próprio governador_c.
    assert linha["peer_mean"] == pytest.approx((100 + 300 + 400) / 3)
    assert linha["delta"] == pytest.approx(200 - (100 + 300 + 400) / 3)
    # 400 e 300 são maiores que 200 -- rank 3 de 4.
    assert linha["rank"] == 3
    assert linha["total"] == 4


def test_rank_1_para_o_maior_valor_da_metrica():
    """Maior valor = rank #1 em todas as métricas -- RECENCIA já vem invertida
    (1/(dias+1)) do EngagementAggregator, então "maior é melhor" vale de forma
    uniforme, sem precisar de direção especial por métrica."""
    out = compute_governor_comparison(
        _df_engagement(), "https://www.instagram.com/governador_d/", METRICS
    )
    linha = out.set_index("metric").loc["% ENGAJAMENTO"]

    assert linha["rank"] == 1
    assert linha["delta"] > 0


def test_peer_mean_exclui_o_proprio_governador_selecionado():
    """Sem excluir o próprio governador da média, quem domina uma métrica
    teria o delta artificialmente reduzido (a própria nota alta puxando a
    média pra cima)."""
    df = pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/dominante/", "https://www.instagram.com/outro/"],
            "followersCount": [1000, 100],
        }
    )
    out = compute_governor_comparison(df, "https://www.instagram.com/dominante/", ["followersCount"])
    linha = out.set_index("metric").loc["followersCount"]

    assert linha["peer_mean"] == 100
    assert linha["delta"] == 900


def test_dataframe_vazio_retorna_vazio_sem_quebrar():
    out = compute_governor_comparison(
        pd.DataFrame(columns=["inputUrl"] + METRICS), "https://www.instagram.com/qualquer/", METRICS
    )
    assert out.empty
    assert list(out.columns) == ["metric", "value", "peer_mean", "delta", "rank", "total"]


def test_governador_sem_linha_correspondente_retorna_vazio_sem_quebrar():
    out = compute_governor_comparison(
        _df_engagement(), "https://www.instagram.com/nao_existe/", METRICS
    )
    assert out.empty


def test_valores_nulos_na_metrica_nao_entram_no_peer_mean_nem_no_total():
    df = _df_engagement()
    df.loc[df["inputUrl"] == "https://www.instagram.com/governador_a/", "% ENGAJAMENTO"] = np.nan

    out = compute_governor_comparison(
        df, "https://www.instagram.com/governador_b/", ["% ENGAJAMENTO"]
    )
    linha = out.set_index("metric").loc["% ENGAJAMENTO"]

    # governador_a (NaN) fica de fora tanto do total quanto do peer_mean.
    assert linha["total"] == 3
    assert linha["peer_mean"] == pytest.approx((2.0 + 4.0) / 2)
