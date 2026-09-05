"""Regressão de performance-por-post: circularidade + preditores + Lasso
vídeo/estático (ADR 0019, parte C)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LassoCV
from sklearn.metrics import r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.modeling.config import PostPerformanceConfig

logger = logging.getLogger(__name__)

GRUPO_VIDEO = "video"
GRUPO_ESTATICO = "estatico"

_DIAS_DA_SEMANA_PT = [
    "segunda",
    "terca",
    "quarta",
    "quinta",
    "sexta",
    "sabado",
    "domingo",
]


class CircularityError(Exception):
    """Preditor circular detectado -- a regressão não deve rodar (ADR 0019,
    decisão 7: é o erro que motivou todo este trabalho)."""


@dataclass
class GroupModelResult:
    grupo: str
    coeficientes: pd.DataFrame
    previsoes: pd.DataFrame
    r2_treino: float
    r2_holdout: float
    n_treino: int
    n_holdout: int
    alpha: float


@dataclass
class PostPerformanceStageResult:
    coefficients: pd.DataFrame
    predictions: pd.DataFrame


def assemble_predictors(
    df_group: pd.DataFrame,
    df_engagement: pd.DataFrame,
    grupo: str,
) -> pd.DataFrame:
    """Monta preditores + Y de um grupo (`GRUPO_VIDEO`/`GRUPO_ESTATICO`) a
    partir do Silver já enriquecido (`type_raw`/`hashtags` da issue A,
    `Topic` da issue B quando presente) e do `governor_engagement` (Gold,
    `_WC_COMENTARIO`/`FREQUENCIA`/`followersCount` por perfil).

    `caption`/`hashtags`/`Topic` só existem hoje em `posts_clean` -- Reels
    não têm campo de caption no Bronze/Silver (limitação estrutural de dado
    coletado, não escolha de design) -- por isso comprimento de legenda e
    Tema só entram quando essas colunas já estão presentes em `df_group`
    (grupo estático).

    Descarta posts cujo perfil não tem `followersCount` positivo em
    `df_engagement` -- sem seguidores não há como calcular a taxa que
    compõe Y (divisão por zero)."""
    df = df_group.copy()

    df["hora_do_dia"] = df["data_hora"].dt.hour
    df["dia_da_semana"] = df["data_hora"].dt.dayofweek.map(dict(enumerate(_DIAS_DA_SEMANA_PT)))
    df["tem_duracao"] = df["videoDuration"].notna().astype(int)
    df["videoDuration"] = df["videoDuration"].fillna(0.0)

    if "caption" in df.columns:
        df["comprimento_legenda"] = df["caption"].fillna("").str.len()

    if grupo == GRUPO_VIDEO:
        df["paidPartnership"] = df["isSponsored"].fillna(False).astype(int)

    # `df_engagement["id"]` é o governador -- renomeado antes do merge para
    # não colidir com o `id` do próprio post/reel já presente em `df`.
    engagement_cols = df_engagement[["id", "_WC_COMENTARIO", "FREQUENCIA", "followersCount"]].rename(
        columns={"id": "_governor_id"}
    )
    df = df.merge(engagement_cols, left_on="ownerId", right_on="_governor_id", how="inner").drop(
        columns=["_governor_id"]
    )

    followers_validos = df["followersCount"].where(df["followersCount"] > 0)
    df["y"] = (df["likesCount"] + df["commentsCount"] * df["_WC_COMENTARIO"]) / followers_validos

    n_antes = len(df)
    df = df.dropna(subset=["y"])
    if len(df) < n_antes:
        logger.debug(
            "assemble_predictors (%s): %d posts descartados por followersCount<=0.",
            grupo,
            n_antes - len(df),
        )

    return df


def resolve_predictor_columns(
    df: pd.DataFrame, config: PostPerformanceConfig, grupo: str
) -> tuple[list[str], list[str]]:
    """Resolve as colunas numéricas/categóricas de um grupo, filtrando às
    que de fato existem em `df` -- `comprimento_legenda`/`Topic` (estático)
    e `videoPlayCount`/`paidPartnership` (vídeo) só entram quando o grupo
    correspondente de fato os produziu (ver `assemble_predictors`)."""
    numeric = list(config.numeric_predictors_comuns)
    categorical = list(config.categorical_predictors_comuns)
    if grupo == GRUPO_VIDEO:
        numeric += config.numeric_predictors_video
        categorical += config.categorical_predictors_video
    else:
        numeric += config.numeric_predictors_estatico
        categorical += config.categorical_predictors_estatico

    numeric = [coluna for coluna in numeric if coluna in df.columns]
    categorical = [coluna for coluna in categorical if coluna in df.columns]
    return numeric, categorical


def check_circularity(
    df: pd.DataFrame,
    y_column: str,
    numeric_predictors: list[str],
    categorical_predictors: list[str],
    raw_target_columns: tuple[str, ...],
    correlation_threshold: float,
) -> None:
    """Falha alto e cedo (ADR 0019, decisão 7) se algum preditor for
    literalmente uma das colunas brutas que compõem Y, ou se a correlação
    bruta entre um preditor numérico e Y ultrapassar `correlation_threshold`."""
    todos_preditores = set(numeric_predictors) | set(categorical_predictors)
    preditores_proibidos = todos_preditores & set(raw_target_columns)
    if preditores_proibidos:
        raise CircularityError(
            f"Preditores derivados das mesmas colunas brutas de Y: "
            f"{sorted(preditores_proibidos)}"
        )

    y = df[y_column]
    for coluna in numeric_predictors:
        # Coluna constante (variância zero, ex.: `tem_duracao` sempre 1 no
        # grupo vídeo) não tem correlação definida -- e não carrega
        # informação nenhuma sobre Y, então não pode ser circular.
        if df[coluna].std(ddof=0) == 0:
            continue
        correlacao = df[coluna].corr(y)
        if pd.notna(correlacao) and abs(correlacao) > correlation_threshold:
            raise CircularityError(
                f"Preditor '{coluna}' tem correlação {correlacao:.3f} com Y "
                f"(limiar: {correlation_threshold}) -- risco de circularidade."
            )


def select_holdout_governors(
    governor_ids: pd.Series, config: PostPerformanceConfig
) -> set[str]:
    """Sorteia o conjunto de governadores em holdout, o mesmo para os dois
    grupos (ADR 0019, decisão 5 -- os dois R² de holdout ficam comparáveis).
    Ordena antes de sortear para que o resultado dependa só de
    `config.random_state`, não da ordem de chegada de `governor_ids`."""
    ids_unicos = sorted(set(governor_ids))
    n_holdout = min(config.holdout_governors_count, len(ids_unicos))
    rng = np.random.default_rng(config.random_state)
    holdout = rng.choice(ids_unicos, size=n_holdout, replace=False)
    return set(holdout)


def train_evaluate_group(
    df: pd.DataFrame,
    grupo: str,
    numeric_predictors: list[str],
    categorical_predictors: list[str],
    holdout_governors: set[str],
    config: PostPerformanceConfig,
) -> GroupModelResult:
    """Ajusta um `Lasso` (alpha por `LassoCV`) sobre o holdout de
    governadores em `holdout_governors`, com `StandardScaler` nos
    preditores numéricos e one-hot nos categóricos. Retorna coeficientes
    por preditor, R² de treino/holdout, e previsão/resíduo por post
    (treino e holdout juntos)."""
    em_holdout = df["ownerId"].isin(holdout_governors)
    df_treino = df.loc[~em_holdout]
    df_holdout = df.loc[em_holdout]

    colunas_preditoras = numeric_predictors + categorical_predictors
    preprocessador = ColumnTransformer(
        [
            ("numericas", StandardScaler(), numeric_predictors),
            (
                "categoricas",
                OneHotEncoder(handle_unknown="ignore"),
                categorical_predictors,
            ),
        ]
    )
    modelo = Pipeline(
        [
            ("preprocessamento", preprocessador),
            (
                "lasso",
                LassoCV(
                    cv=min(config.lasso_cv_folds, len(df_treino)),
                    random_state=config.random_state,
                    max_iter=config.lasso_max_iter,
                ),
            ),
        ]
    )

    X_treino = df_treino[colunas_preditoras]
    y_treino = df_treino["y"]
    modelo.fit(X_treino, y_treino)

    y_treino_previsto = modelo.predict(X_treino)
    r2_treino = r2_score(y_treino, y_treino_previsto)

    previsoes_partes = [
        pd.DataFrame(
            {
                "id": df_treino["id"].to_numpy(),
                "inputUrl": df_treino["inputUrl"].to_numpy(),
                "y_real": y_treino.to_numpy(),
                "y_previsto": y_treino_previsto,
            }
        )
    ]

    if len(df_holdout) > 0:
        X_holdout = df_holdout[colunas_preditoras]
        y_holdout = df_holdout["y"]
        y_holdout_previsto = modelo.predict(X_holdout)
        r2_holdout = r2_score(y_holdout, y_holdout_previsto)
        previsoes_partes.append(
            pd.DataFrame(
                {
                    "id": df_holdout["id"].to_numpy(),
                    "inputUrl": df_holdout["inputUrl"].to_numpy(),
                    "y_real": y_holdout.to_numpy(),
                    "y_previsto": y_holdout_previsto,
                }
            )
        )
    else:
        # Amostra pequena demais/holdout sem posts deste grupo -- degrada
        # para NaN em vez de dividir por zero postos em holdout.
        r2_holdout = float("nan")

    previsoes = pd.concat(previsoes_partes, ignore_index=True)
    previsoes["grupo"] = grupo
    previsoes["residuo"] = previsoes["y_real"] - previsoes["y_previsto"]

    nomes_features = modelo.named_steps["preprocessamento"].get_feature_names_out()
    coeficientes = pd.DataFrame(
        {
            "grupo": grupo,
            "preditor": nomes_features,
            "coeficiente": modelo.named_steps["lasso"].coef_,
            "r2_treino": r2_treino,
            "r2_holdout": r2_holdout,
            "n_treino": len(df_treino),
            "n_holdout": len(df_holdout),
            "alpha": modelo.named_steps["lasso"].alpha_,
        }
    )

    return GroupModelResult(
        grupo=grupo,
        coeficientes=coeficientes,
        previsoes=previsoes,
        r2_treino=r2_treino,
        r2_holdout=r2_holdout,
        n_treino=len(df_treino),
        n_holdout=len(df_holdout),
        alpha=modelo.named_steps["lasso"].alpha_,
    )


def run_post_performance_stage(
    df_posts: pd.DataFrame,
    df_reels: pd.DataFrame,
    df_engagement: pd.DataFrame,
    config: PostPerformanceConfig,
) -> PostPerformanceStageResult:
    """Treina os dois grupos (vídeo=Reels, estático=Posts) com o mesmo
    holdout de governadores, e junta coeficientes/previsões dos dois num
    par de DataFrames prontos para `ModelEnricher.write_post_performance_*`.

    `df_posts` precisa já ter passado por
    `src.modeling.topics.classify_post_topics` (issue B) -- é de lá que vem
    a coluna `Topic` (Tema)."""
    holdout_governors = select_holdout_governors(df_engagement["id"], config)

    resultados: list[GroupModelResult] = []
    for df_group, grupo in ((df_reels, GRUPO_VIDEO), (df_posts, GRUPO_ESTATICO)):
        df_assemblado = assemble_predictors(df_group, df_engagement, grupo)
        numeric_predictors, categorical_predictors = resolve_predictor_columns(
            df_assemblado, config, grupo
        )
        check_circularity(
            df_assemblado,
            "y",
            numeric_predictors,
            categorical_predictors,
            config.raw_target_columns,
            config.circularity_correlation_threshold,
        )
        resultados.append(
            train_evaluate_group(
                df_assemblado,
                grupo,
                numeric_predictors,
                categorical_predictors,
                holdout_governors,
                config,
            )
        )

    coefficients = pd.concat([r.coeficientes for r in resultados], ignore_index=True)
    predictions = pd.concat([r.previsoes for r in resultados], ignore_index=True)
    return PostPerformanceStageResult(coefficients=coefficients, predictions=predictions)
