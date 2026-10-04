"""
Escore composto (Scorecard) dos governadores (ADR 0030, issue #184 / spec #182).

Segue a metodologia de indicadores compostos (OECD Handbook): indicador bruto
-> normalizacao -> ponderacao -> agregacao. Estagio pos-modelagem proprio,
fora do `EngagementAggregator` (ver `scripts/run_governor_scorecard.py` e o
registro em `src/modeling/orchestration.py`); le Silver/Gold ja prontos e grava
`governor_scorecard` (uma linha por governador, modo overwrite).

Dimensoes por governador (chave de juncao: `inputUrl` normalizado, ver
`normalize_input_url`):

1. **Alcance** = media de `videoPlayCount` dos REELS do perfil. Posts de feed
   nao tem plays (Instagram nao expoe), por isso so reels entram. O nome
   correto e "reproducoes/plays" -- NUNCA "visualizacoes unicas".
2. **Ativacao** = media de `likesCount` dos reels / `followersCount` do perfil.
3. **Qualidade** = comentarios positivos / comentarios totais do perfil
   (somente linhas `fonte == "comentario"` de `governor_sentiment`; legenda e
   transcricao nao contam).
4. **Profundidade** = media de `commentsCount` / media de `videoPlayCount`,
   ambas sobre os reels com plays informados (mesma base do Alcance).
5. **Consistencia** = CMGR de engajamento por data de publicacao (ADR 0030),
   ver `compute_cmgr_engajamento` e as constantes abaixo.

Normalizacao: min-max 0-100 entre os perfis (`min_max_normalize`).
Dimensao pendente/nula de um perfil nao entra no min-max daquela dimensao.

Agregacao: soma ponderada com pesos iguais. Com as 5 dimensoes, 0,20 cada;
com uma dimensao pendente (caso previsto: Consistencia), os pesos sao
renormalizados para 1/n (0,25 cada com 4). `n_dimensoes` registra quantas
entraram. Abaixo de `MIN_DIMENSOES_PARA_ESCORE` o escore e nulo (perfil sem
dado suficiente nao ganha um escore enganoso) e nao entra no ranking.

Convencoes de "nao calculavel": nunca excecao, nunca divisao por zero --
dimensao indefinida vira `NaN` (coluna `float64` nullable no Gold), como em
`src/modeling/growth_history.py`.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.delta_io import write_delta
from src.schemas_delta import GOLD_GOVERNOR_SCORECARD_SCHEMA

# --- Consistencia (ADR 0030): parametros fixos desta decisao ---------------
# Janela maxima de meses COMPLETOS recentes (o mes corrente fica de fora).
JANELA_MAX_MESES = 12
# Um mes so conta com pelo menos este numero de posts (media de poucos posts
# e ruido).
MIN_POSTS_POR_MES = 3
# Menos de 4 meses validos -> Consistencia pendente (regressao sobre <4
# pontos nao tem significado).
MIN_MESES_VALIDOS = 4
# Posts com menos de 7 dias de vida sao excluidos: ainda acumulam curtidas
# (vies de maturidade).
MIN_DIAS_DE_VIDA = 7

# Perfil precisa de pelo menos 4 das 5 dimensoes para ter escore.
MIN_DIMENSOES_PARA_ESCORE = 4
# Todos os perfis iguais em uma dimensao (amplitude zero): valor neutro 50 --
# sem diferenciacao nao ha motivo para premiar (100) ou punir (0).
VALOR_AMPLITUDE_ZERO = 50.0

DIMENSOES = ["alcance", "ativacao", "qualidade", "profundidade", "consistencia"]

_POST_COLUMNS = ["id", "inputUrl", "likesCount", "commentsCount", "data_hora"]
_RESULT_COLUMNS = (
    ["inputUrl", "username"]
    + DIMENSOES
    + [f"{d}_norm" for d in DIMENSOES]
    + [
        "consistencia_pendente",
        "consistencia_n_meses",
        "n_dimensoes",
        "escore",
        "ranking",
    ]
)


def normalize_input_url(value) -> str | None:
    """Chave de juncao de perfil: minusculas, sem espacos e sem barra final.
    `None`/`NaN` -> `None`."""
    if value is None or pd.isna(value):
        return None
    return str(value).strip().lower().rstrip("/")


def min_max_normalize(values: pd.Series) -> pd.Series:
    """`100 * (x - min) / (max - min)` entre os valores nao nulos; nulos
    continuam nulos. Amplitude zero (todos iguais, ou um unico valor) ->
    `VALOR_AMPLITUDE_ZERO`, nunca divisao por zero."""
    values = pd.to_numeric(values, errors="coerce").astype("float64")
    valid = values.dropna()
    if valid.empty:
        return values
    low, high = valid.min(), valid.max()
    if high == low:
        return values.where(values.isna(), VALOR_AMPLITUDE_ZERO)
    return 100.0 * (values - low) / (high - low)


def compute_cmgr_engajamento(
    df_posts: pd.DataFrame, now: pd.Timestamp
) -> tuple[float, int]:
    """CMGR de engajamento por data de publicacao de UM perfil (ADR 0030).

    `df_posts`: posts do perfil com `likesCount`, `commentsCount`, `data_hora`
    (engajamento do post = curtidas + comentarios). Retorna
    `(taxa_mensal, n_meses_validos)`; `taxa_mensal = exp(inclinacao) - 1` da
    regressao log-linear sobre o engajamento medio por post de cada mes
    valido, ou `NaN` quando ha menos de `MIN_MESES_VALIDOS` meses validos.
    Mes valido: dentro da janela de `JANELA_MAX_MESES` meses completos antes
    do mes de `now`, com >= `MIN_POSTS_POR_MES` posts maduros
    (>= `MIN_DIAS_DE_VIDA` dias) e media positiva (log definido)."""
    if df_posts.empty:
        return float("nan"), 0

    working = df_posts[["likesCount", "commentsCount", "data_hora"]].copy()
    # `data_hora` pode chegar tz-aware: normaliza para UTC naive (comparavel a `now`).
    working["data_hora"] = pd.to_datetime(
        working["data_hora"], errors="coerce", utc=True
    ).dt.tz_localize(None)
    working = working.dropna(subset=["data_hora"])
    working["engajamento"] = pd.to_numeric(
        working["likesCount"], errors="coerce"
    ).fillna(0) + pd.to_numeric(working["commentsCount"], errors="coerce").fillna(0)

    now = pd.Timestamp(now)
    maduros = working[
        working["data_hora"] <= now - pd.Timedelta(days=MIN_DIAS_DE_VIDA)
    ].copy()
    maduros["mes"] = maduros["data_hora"].dt.to_period("M")

    mes_corrente = now.to_period("M")
    maduros = maduros[
        (maduros["mes"] < mes_corrente)
        & (maduros["mes"] >= mes_corrente - JANELA_MAX_MESES)
    ]
    if maduros.empty:
        return float("nan"), 0

    mensal = maduros.groupby("mes")["engajamento"].agg(["mean", "size"])
    mensal = mensal[(mensal["size"] >= MIN_POSTS_POR_MES) & (mensal["mean"] > 0)]
    n_meses = len(mensal)
    if n_meses < MIN_MESES_VALIDOS:
        return float("nan"), n_meses

    x = np.array([m.ordinal for m in mensal.index], dtype="float64")
    y = np.log(mensal["mean"].to_numpy(dtype="float64"))
    inclinacao = np.polyfit(x, y, 1)[0]
    return float(math.exp(inclinacao) - 1.0), n_meses


def _require(df: pd.DataFrame, columns: set[str], nome: str) -> None:
    missing = columns - set(df.columns)
    if missing:
        raise ValueError(f"{nome} não tem as colunas esperadas: {sorted(missing)}")


def _safe_div(numerator: float, denominator: float) -> float:
    if (
        denominator is None
        or pd.isna(denominator)
        or denominator <= 0
        or pd.isna(numerator)
    ):
        return float("nan")
    return float(numerator) / float(denominator)


class GovernorScorecardScorer:
    def score(
        self,
        df_profiles: pd.DataFrame,
        df_reels: pd.DataFrame,
        df_posts: pd.DataFrame,
        df_sentiment: pd.DataFrame,
        now: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """Calcula o Escore composto. `df_profiles` e `governor_engagement`
        (um perfil por linha, `followersCount`); `df_reels`/`df_posts` sao a
        Silver (`reels_clean`/`posts_clean`); `df_sentiment` e
        `governor_sentiment`. `now` explicito para teste determinístico
        (default: agora, UTC). Uma linha por perfil de `df_profiles`,
        ordenada por ranking (perfis sem escore ao final)."""
        _require(df_profiles, {"inputUrl", "followersCount"}, "df_profiles")
        _require(
            df_reels,
            {"inputUrl", "videoPlayCount", "likesCount", "commentsCount"},
            "df_reels",
        )
        _require(df_posts, set(_POST_COLUMNS), "df_posts")
        _require(df_sentiment, {"inputUrl", "sentiment_label"}, "df_sentiment")

        if now is None:
            now = pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))

        perfis = df_profiles.dropna(subset=["inputUrl"]).copy()
        perfis["_key"] = perfis["inputUrl"].map(normalize_input_url)
        perfis = perfis.drop_duplicates(subset="_key").reset_index(drop=True)

        reels = df_reels.copy()
        reels["_key"] = reels["inputUrl"].map(normalize_input_url)
        for col in ("videoPlayCount", "likesCount", "commentsCount"):
            reels[col] = pd.to_numeric(reels[col], errors="coerce")
        reels_por_perfil = {k: g for k, g in reels.groupby("_key")}

        # Posts de feed e reels se sobrepoem na Silver (um reel tambem e
        # capturado pelo scraper de posts): deduplica por `id`.
        todos = pd.concat(
            [df_posts[_POST_COLUMNS], df_reels.reindex(columns=_POST_COLUMNS)]
        )
        # `id` nulo nao identifica o post: so deduplica linhas com `id`.
        todos = pd.concat(
            [
                todos[todos["id"].isna()],
                todos[todos["id"].notna()].drop_duplicates(subset="id"),
            ]
        )
        todos["_key"] = todos["inputUrl"].map(normalize_input_url)
        posts_por_perfil = {k: g for k, g in todos.groupby("_key")}

        sent = df_sentiment.copy()
        if "fonte" in sent.columns:
            sent = sent[sent["fonte"] == "comentario"]
        sent["_key"] = sent["inputUrl"].map(normalize_input_url)
        sent = sent.dropna(subset=["_key"])
        sent["_positivo"] = (
            sent["sentiment_label"].astype(str).str.lower() == "positive"
        )
        comentarios = sent.groupby("_key")["_positivo"].agg(["sum", "size"])

        empty_reels = reels.iloc[0:0]
        empty_posts = todos.iloc[0:0]
        linhas = []
        for _, perfil in perfis.iterrows():
            key = perfil["_key"]
            r = reels_por_perfil.get(key, empty_reels)
            r_plays = r.dropna(subset=["videoPlayCount"])

            alcance = (
                float(r_plays["videoPlayCount"].mean())
                if len(r_plays)
                else float("nan")
            )
            likes_medio = (
                r["likesCount"].mean()
                if r["likesCount"].notna().any()
                else float("nan")
            )
            ativacao = _safe_div(
                likes_medio, pd.to_numeric(perfil["followersCount"], errors="coerce")
            )
            comentarios_medio = (
                r_plays["commentsCount"].mean()
                if r_plays["commentsCount"].notna().any()
                else float("nan")
            )
            profundidade = _safe_div(comentarios_medio, alcance)

            if key in comentarios.index:
                qualidade = _safe_div(
                    comentarios.loc[key, "sum"], comentarios.loc[key, "size"]
                )
            else:
                qualidade = float("nan")

            consistencia, n_meses = compute_cmgr_engajamento(
                posts_por_perfil.get(key, empty_posts), now
            )

            linhas.append(
                {
                    "inputUrl": perfil["inputUrl"],
                    "username": perfil["username"]
                    if "username" in perfil.index
                    else None,
                    "alcance": alcance,
                    "ativacao": ativacao,
                    "qualidade": qualidade,
                    "profundidade": profundidade,
                    "consistencia": consistencia,
                    "consistencia_n_meses": n_meses,
                }
            )

        out = pd.DataFrame(
            linhas,
            columns=["inputUrl", "username", *DIMENSOES, "consistencia_n_meses"],
        )
        for dim in DIMENSOES:
            out[dim] = out[dim].astype("float64")
            out[f"{dim}_norm"] = min_max_normalize(out[dim])

        normalizadas = out[[f"{d}_norm" for d in DIMENSOES]]
        out["n_dimensoes"] = normalizadas.notna().sum(axis=1).astype("int64")
        out["consistencia_pendente"] = out["consistencia"].isna()
        # Media simples das dimensoes disponiveis == soma ponderada com pesos
        # iguais renormalizados (0,20 com 5; 0,25 com 4).
        out["escore"] = normalizadas.mean(axis=1, skipna=True).where(
            out["n_dimensoes"] >= MIN_DIMENSOES_PARA_ESCORE
        )

        out = out.sort_values(
            ["escore", "inputUrl"],
            ascending=[False, True],
            na_position="last",
            kind="stable",
        ).reset_index(drop=True)
        ranking = pd.Series(range(1, len(out) + 1), index=out.index, dtype="Int64")
        out["ranking"] = ranking.where(out["escore"].notna())
        return out[_RESULT_COLUMNS]

    def write(
        self,
        df_scored: pd.DataFrame,
        path: Path | str,
        run_id: str,
        mode: str = "overwrite",
        generated_at: datetime | None = None,
    ) -> None:
        """Grava `governor_scorecard` (saida de `score()`), validando o
        contrato `GOLD_GOVERNOR_SCORECARD_SCHEMA` (fail-fast)."""
        df = df_scored.copy()
        df["_run_id"] = run_id
        df["_generated_at"] = generated_at or datetime.now(timezone.utc)
        write_delta(path, df, GOLD_GOVERNOR_SCORECARD_SCHEMA, mode=mode)
