import numpy as np
import pandas as pd
import pytest

from src.modeling.config import PostPerformanceConfig
from src.modeling.post_performance import (
    GRUPO_ESTATICO,
    GRUPO_VIDEO,
    CircularityError,
    assemble_predictors,
    check_circularity,
    resolve_predictor_columns,
    run_post_performance_stage,
    select_holdout_governors,
    train_evaluate_group,
)

N_GOVERNADORES = 12
POSTS_POR_GOVERNADOR = 6


def _config(**overrides):
    defaults = {"holdout_governors_count": 3, "lasso_cv_folds": 3}
    defaults.update(overrides)
    return PostPerformanceConfig(**defaults)


def _df_engagement():
    rng = np.random.default_rng(0)
    ids = [f"gov{i}" for i in range(N_GOVERNADORES)]
    return pd.DataFrame(
        {
            "id": ids,
            "_WC_COMENTARIO": 1.5,
            "FREQUENCIA": rng.uniform(0.1, 2.0, size=N_GOVERNADORES),
            "followersCount": rng.integers(10_000, 500_000, size=N_GOVERNADORES),
        }
    )


def _df_reels(df_engagement):
    rng = np.random.default_rng(1)
    linhas = []
    for gov in df_engagement["id"]:
        for j in range(POSTS_POR_GOVERNADOR):
            linhas.append(
                {
                    "id": f"{gov}_reel_{j}",
                    "ownerId": gov,
                    "ownerUsername": gov,
                    "inputUrl": f"https://instagram.com/{gov}",
                    "commentsCount": int(rng.integers(0, 200)),
                    "likesCount": int(rng.integers(0, 5000)),
                    "data_hora": pd.Timestamp("2026-01-01")
                    + pd.Timedelta(days=j, hours=int(rng.integers(0, 24))),
                    "type_raw": "Video",
                    "videoDuration": float(rng.uniform(5, 90)),
                    "videoPlayCount": int(rng.integers(100, 100_000)),
                    "isSponsored": bool(rng.integers(0, 2)),
                }
            )
    return pd.DataFrame(linhas)


def _df_posts(df_engagement):
    rng = np.random.default_rng(2)
    linhas = []
    for gov in df_engagement["id"]:
        for j in range(POSTS_POR_GOVERNADOR):
            linhas.append(
                {
                    "id": f"{gov}_post_{j}",
                    "ownerId": gov,
                    "ownerUsername": gov,
                    "inputUrl": f"https://instagram.com/{gov}",
                    "commentsCount": int(rng.integers(0, 200)),
                    "likesCount": int(rng.integers(0, 5000)),
                    "data_hora": pd.Timestamp("2026-01-01")
                    + pd.Timedelta(days=j, hours=int(rng.integers(0, 24))),
                    "type_raw": rng.choice(["Image", "Sidecar"]),
                    "videoDuration": np.nan,
                    "caption": f"legenda {j} do governador {gov}",
                    "hashtags": '["politica"]',
                    "Topic": int(rng.integers(0, 3)),
                }
            )
    return pd.DataFrame(linhas)


def test_check_circularity_dispara_quando_preditor_e_coluna_bruta_de_y():
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0], "likesCount": [10, 20, 30]})
    with pytest.raises(CircularityError):
        check_circularity(df, "y", ["likesCount"], [], ("likesCount", "commentsCount"), 0.95)


def test_check_circularity_dispara_quando_correlacao_ultrapassa_limiar():
    y = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    df = pd.DataFrame({"y": y, "preditor_circular": y * 2 + 0.001})
    with pytest.raises(CircularityError):
        check_circularity(
            df, "y", ["preditor_circular"], [], ("likesCount", "commentsCount"), 0.95
        )


def test_check_circularity_passa_com_preditores_sem_correlacao_alta():
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0, 4.0], "hora_do_dia": [10, 20, 5, 15]})
    check_circularity(df, "y", ["hora_do_dia"], [], ("likesCount", "commentsCount"), 0.95)


def test_select_holdout_governors_e_reproduzivel_e_respeita_contagem():
    ids = pd.Series([f"gov{i}" for i in range(10)])
    config = _config(holdout_governors_count=3)

    holdout1 = select_holdout_governors(ids, config)
    holdout2 = select_holdout_governors(ids, config)

    assert holdout1 == holdout2
    assert len(holdout1) == 3
    assert holdout1 <= set(ids)


def test_assemble_predictors_video_nao_tem_comprimento_legenda_nem_tema():
    df_engagement = _df_engagement()
    df = assemble_predictors(_df_reels(df_engagement), df_engagement, GRUPO_VIDEO)

    assert "comprimento_legenda" not in df.columns
    assert "paidPartnership" in df.columns
    assert "y" in df.columns
    assert df["y"].notna().all()


def test_assemble_predictors_estatico_tem_comprimento_legenda_e_nao_tem_preditores_de_video():
    df_engagement = _df_engagement()
    df = assemble_predictors(_df_posts(df_engagement), df_engagement, GRUPO_ESTATICO)

    assert "comprimento_legenda" in df.columns
    assert "paidPartnership" not in df.columns
    assert "y" in df.columns


def test_assemble_predictors_descarta_posts_de_governador_sem_seguidores():
    df_engagement = _df_engagement()
    df_engagement.loc[0, "followersCount"] = 0
    df_posts = _df_posts(df_engagement)
    governador_sem_seguidores = df_engagement.loc[0, "id"]

    df = assemble_predictors(df_posts, df_engagement, GRUPO_ESTATICO)

    assert governador_sem_seguidores not in set(df["ownerId"])
    assert len(df) == len(df_posts) - POSTS_POR_GOVERNADOR


def test_resolve_predictor_columns_video_vs_estatico():
    df_engagement = _df_engagement()
    config = _config()

    df_video = assemble_predictors(_df_reels(df_engagement), df_engagement, GRUPO_VIDEO)
    numeric_v, categorical_v = resolve_predictor_columns(df_video, config, GRUPO_VIDEO)
    assert "videoPlayCount" in numeric_v
    assert "paidPartnership" in numeric_v
    assert "comprimento_legenda" not in numeric_v
    assert "Topic" not in categorical_v

    df_estatico = assemble_predictors(_df_posts(df_engagement), df_engagement, GRUPO_ESTATICO)
    numeric_e, categorical_e = resolve_predictor_columns(df_estatico, config, GRUPO_ESTATICO)
    assert "comprimento_legenda" in numeric_e
    assert "Topic" in categorical_e
    assert "videoPlayCount" not in numeric_e
    assert "paidPartnership" not in numeric_e


def test_train_evaluate_group_isola_governador_do_holdout_de_um_lado_so():
    df_engagement = _df_engagement()
    config = _config()
    df_assemblado = assemble_predictors(_df_posts(df_engagement), df_engagement, GRUPO_ESTATICO)
    numeric, categorical = resolve_predictor_columns(df_assemblado, config, GRUPO_ESTATICO)
    holdout = select_holdout_governors(df_engagement["id"], config)

    resultado = train_evaluate_group(
        df_assemblado, GRUPO_ESTATICO, numeric, categorical, holdout, config
    )

    em_holdout = df_assemblado["ownerId"].isin(holdout)
    ids_holdout_esperados = set(df_assemblado.loc[em_holdout, "id"])
    ids_treino_esperados = set(df_assemblado.loc[~em_holdout, "id"])

    assert set(resultado.previsoes["id"]) == ids_holdout_esperados | ids_treino_esperados
    assert resultado.n_treino == len(ids_treino_esperados)
    assert resultado.n_holdout == len(ids_holdout_esperados)
    assert isinstance(resultado.r2_treino, float)
    assert isinstance(resultado.r2_holdout, float)

    # issue #76: os notebooks de diagnóstico precisam filtrar só os
    # resíduos de holdout -- a coluna `conjunto` é o que permite isso sem
    # reimplementar o split aqui.
    previsoes_por_conjunto = resultado.previsoes.set_index("id")["conjunto"]
    ids_marcados_holdout = set(previsoes_por_conjunto[previsoes_por_conjunto == "holdout"].index)
    ids_marcados_treino = set(previsoes_por_conjunto[previsoes_por_conjunto == "treino"].index)
    assert ids_marcados_holdout == ids_holdout_esperados
    assert ids_marcados_treino == ids_treino_esperados


def test_train_evaluate_group_produz_coeficientes_por_preditor():
    df_engagement = _df_engagement()
    config = _config()
    df_assemblado = assemble_predictors(_df_reels(df_engagement), df_engagement, GRUPO_VIDEO)
    numeric, categorical = resolve_predictor_columns(df_assemblado, config, GRUPO_VIDEO)
    holdout = select_holdout_governors(df_engagement["id"], config)

    resultado = train_evaluate_group(
        df_assemblado, GRUPO_VIDEO, numeric, categorical, holdout, config
    )

    colunas_esperadas = {
        "grupo",
        "preditor",
        "coeficiente",
        "r2_treino",
        "r2_holdout",
        "n_treino",
        "n_holdout",
        "alpha",
    }
    assert colunas_esperadas <= set(resultado.coeficientes.columns)
    assert (resultado.coeficientes["grupo"] == GRUPO_VIDEO).all()
    assert len(resultado.coeficientes) > 0


def test_run_post_performance_stage_end_to_end():
    df_engagement = _df_engagement()
    df_reels = _df_reels(df_engagement)
    df_posts = _df_posts(df_engagement)
    config = _config()

    resultado = run_post_performance_stage(df_posts, df_reels, df_engagement, config)

    assert set(resultado.coefficients["grupo"].unique()) == {GRUPO_VIDEO, GRUPO_ESTATICO}
    assert set(resultado.predictions["grupo"].unique()) == {GRUPO_VIDEO, GRUPO_ESTATICO}
    assert len(resultado.predictions) == len(df_reels) + len(df_posts)
    assert {"id", "inputUrl", "grupo", "y_real", "y_previsto", "residuo"} <= set(
        resultado.predictions.columns
    )


def test_run_post_performance_stage_usa_o_mesmo_holdout_nos_dois_grupos():
    """ADR 0019, decisão 5 / user story 9: o holdout de governadores precisa
    ser o mesmo conjunto para vídeo e estático, para que os dois R² de
    holdout sejam comparáveis -- não só do mesmo tamanho por coincidência."""
    df_engagement = _df_engagement()
    df_reels = _df_reels(df_engagement)
    df_posts = _df_posts(df_engagement)
    config = _config()

    holdout_esperado = select_holdout_governors(df_engagement["id"], config)
    resultado = run_post_performance_stage(df_posts, df_reels, df_engagement, config)

    n_holdout_video_esperado = int(df_reels["ownerId"].isin(holdout_esperado).sum())
    n_holdout_estatico_esperado = int(df_posts["ownerId"].isin(holdout_esperado).sum())

    coef_video = resultado.coefficients[resultado.coefficients["grupo"] == GRUPO_VIDEO]
    coef_estatico = resultado.coefficients[resultado.coefficients["grupo"] == GRUPO_ESTATICO]

    assert coef_video["n_holdout"].iloc[0] == n_holdout_video_esperado
    assert coef_estatico["n_holdout"].iloc[0] == n_holdout_estatico_esperado


def test_check_circularity_passa_com_preditores_reais_do_grupo_video():
    df_engagement = _df_engagement()
    config = _config()
    df_assemblado = assemble_predictors(_df_reels(df_engagement), df_engagement, GRUPO_VIDEO)
    numeric, categorical = resolve_predictor_columns(df_assemblado, config, GRUPO_VIDEO)

    check_circularity(
        df_assemblado,
        "y",
        numeric,
        categorical,
        config.raw_target_columns,
        config.circularity_correlation_threshold,
    )


def test_check_circularity_passa_com_preditores_reais_do_grupo_estatico():
    df_engagement = _df_engagement()
    config = _config()
    df_assemblado = assemble_predictors(_df_posts(df_engagement), df_engagement, GRUPO_ESTATICO)
    numeric, categorical = resolve_predictor_columns(df_assemblado, config, GRUPO_ESTATICO)

    check_circularity(
        df_assemblado,
        "y",
        numeric,
        categorical,
        config.raw_target_columns,
        config.circularity_correlation_threshold,
    )
