import numpy as np
import pandas as pd
import pytest

from src.dashboard.comparisons import compute_engagement_quadrants, compute_governor_comparison

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


# --- compute_engagement_quadrants (ADR 0018) ---


def _df_quadrantes():
    """5 governadores desenhados para cair um em cada quadrante, mais um
    exatamente na mediana dos dois eixos (gov_mediano) -- mediana de
    followersCount é 500 (gov_mediano), de % ENGAJAMENTO é 0.05 (também
    gov_mediano). "Alto"/"alta" é estritamente > mediana, então o próprio
    ponto da mediana cai do lado "baixo" nos dois eixos."""
    return pd.DataFrame(
        {
            "inputUrl": [
                "https://www.instagram.com/gov_inexpressivo/",
                "https://www.instagram.com/gov_gigante/",
                "https://www.instagram.com/gov_mediano/",
                "https://www.instagram.com/gov_nicho/",
                "https://www.instagram.com/gov_superstar/",
            ],
            "followersCount": [100, 900, 500, 200, 800],
            "% ENGAJAMENTO": [0.01, 0.02, 0.05, 0.20, 0.30],
        }
    )


def _quadrante_de(out: pd.DataFrame, url: str) -> str:
    return out.set_index("inputUrl").loc[url, "quadrante"]


def test_baixa_audiencia_baixo_engajamento_e_inexpressivo():
    out = compute_engagement_quadrants(_df_quadrantes())
    assert _quadrante_de(out, "https://www.instagram.com/gov_inexpressivo/") == "Inexpressivo"


def test_alta_audiencia_baixo_engajamento_e_gigante_adormecido():
    out = compute_engagement_quadrants(_df_quadrantes())
    assert _quadrante_de(out, "https://www.instagram.com/gov_gigante/") == "Gigante Adormecido"


def test_baixa_audiencia_alto_engajamento_e_nicho():
    out = compute_engagement_quadrants(_df_quadrantes())
    assert _quadrante_de(out, "https://www.instagram.com/gov_nicho/") == "Nicho"


def test_alta_audiencia_alto_engajamento_e_superstar():
    out = compute_engagement_quadrants(_df_quadrantes())
    assert _quadrante_de(out, "https://www.instagram.com/gov_superstar/") == "Superstar"


def test_governador_exatamente_na_mediana_cai_do_lado_baixo():
    """"Alto"/"alta" é estritamente > mediana -- o próprio ponto que define a
    mediana não pode ficar "acima de si mesmo", então cai em Inexpressivo."""
    out = compute_engagement_quadrants(_df_quadrantes())
    assert _quadrante_de(out, "https://www.instagram.com/gov_mediano/") == "Inexpressivo"


def test_medianas_calculadas_aparecem_como_colunas_de_contexto():
    out = compute_engagement_quadrants(_df_quadrantes())
    assert (out["mediana_followers"] == 500).all()
    assert out["mediana_engajamento"].unique() == pytest.approx([0.05])


def test_quadrantes_dataframe_vazio_retorna_vazio_sem_quebrar():
    out = compute_engagement_quadrants(pd.DataFrame(columns=["inputUrl", "followersCount", "% ENGAJAMENTO"]))
    assert out.empty
    assert list(out.columns) == [
        "inputUrl",
        "followersCount",
        "% ENGAJAMENTO",
        "quadrante",
        "mediana_followers",
        "mediana_engajamento",
    ]


def test_quadrantes_uma_linha_so_retorna_vazio_mediana_sem_sentido():
    df = _df_quadrantes().iloc[[0]]
    out = compute_engagement_quadrants(df)
    assert out.empty


def test_quadrantes_sem_colunas_necessarias_retorna_vazio_sem_quebrar():
    """Chamadores como `check_engagement_quadrant` (recommendations.py)
    recebem `df_engagement` com um subconjunto de colunas diferente por
    teste -- ausência de followersCount/% ENGAJAMENTO degrada, não quebra."""
    df = pd.DataFrame({"inputUrl": ["a", "b"], "FREQUENCIA": [1.0, 2.0]})
    out = compute_engagement_quadrants(df)
    assert out.empty


def test_quadrantes_ignora_linhas_com_valor_nulo():
    df = _df_quadrantes()
    df.loc[df["inputUrl"] == "https://www.instagram.com/gov_mediano/", "followersCount"] = np.nan
    out = compute_engagement_quadrants(df)
    assert "https://www.instagram.com/gov_mediano/" not in out["inputUrl"].values
    assert len(out) == 4
