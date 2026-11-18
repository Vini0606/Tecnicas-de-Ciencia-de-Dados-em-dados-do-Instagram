"""
Escore composto (Scorecard) dos governadores (ADR 0030 / ADR 0047, issue #184 /
spec #182).

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
5. **Consistencia** = taxa mensal de variacao do engajamento por publicacao,
   estimada por regressao sobre as publicacoes do proprio perfil (ADR 0047),
   ver `estimar_tendencia_engajamento` e as constantes abaixo. A mesma
   estimativa alimenta a **Tendencia do engajamento** (quatro estados do
   verbete "Tendencia" do CONTEXT.md).

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
import statsmodels.api as sm

from src.delta_io import write_delta
from src.schemas_delta import GOLD_GOVERNOR_SCORECARD_SCHEMA

# --- Consistencia / Tendencia (ADR 0047): parametros fixos desta decisao -----
# Publicacoes com menos de 7 dias de vida sao excluidas: ainda acumulam
# curtidas (vies de maturidade).
MIN_DIAS_DE_VIDA = 7
# Estimativa confiavel so com pelo menos 15 publicacoes maduras...
MIN_PUBLICACOES = 15
# ...espalhadas por pelo menos 10 dias distintos (publicacoes concentradas em
# poucos dias nao sustentam uma inclinacao no tempo).
MIN_DIAS_DISTINTOS = 10
# Subindo/Caindo exigem IC de 95% fora do zero E taxa mensal de pelo menos
# +-5% (efeito pequeno demais nao vira seta).
MIN_EFEITO_MENSAL = 0.05
NIVEL_CONFIANCA = 0.95
# `t` da regressao = dias desde a primeira publicacao do perfil / 30: a
# inclinacao fica em escala mensal.
DIAS_POR_MES = 30.0

# Os quatro estados da Tendencia -- exatamente os rotulos do verbete
# "Tendencia" do CONTEXT.md (sao rotulos de usuario, gravados no Gold).
TENDENCIA_SUBINDO = "Subindo"
TENDENCIA_CAINDO = "Caindo"
TENDENCIA_ESTAVEL = "Estável"
TENDENCIA_DADOS_INSUFICIENTES = "Dados insuficientes"
ESTADOS_TENDENCIA = (
    TENDENCIA_SUBINDO,
    TENDENCIA_CAINDO,
    TENDENCIA_ESTAVEL,
    TENDENCIA_DADOS_INSUFICIENTES,
)

# Perfil precisa de pelo menos 4 das 5 dimensoes para ter escore.
MIN_DIMENSOES_PARA_ESCORE = 4
# Todos os perfis iguais em uma dimensao (amplitude zero): valor neutro 50 --
# sem diferenciacao nao ha motivo para premiar (100) ou punir (0).
VALOR_AMPLITUDE_ZERO = 50.0

DIMENSOES = ["alcance", "ativacao", "qualidade", "profundidade", "consistencia"]

_POST_COLUMNS = ["id", "inputUrl", "likesCount", "commentsCount", "data_hora"]
# Colunas opcionais da Silver usadas pela Consistencia: `isPinned` (ADR 0041,
# fixadas ficam fora) e `Tipo` (FEED/REELS: um reel capturado so pelo scraper
# de posts ainda e tratado como reel).
_POST_OPTIONAL_COLUMNS = ["isPinned", "Tipo"]
_CONSISTENCIA_COLUMNS = [
    "consistencia_taxa_mensal",
    "consistencia_ic_inferior",
    "consistencia_ic_superior",
    "consistencia_n_publicacoes",
    "consistencia_n_dias",
    "tendencia_engajamento",
]
_RESULT_COLUMNS = (
    ["inputUrl", "username"]
    + DIMENSOES
    + [f"{d}_norm" for d in DIMENSOES]
    + ["consistencia_pendente"]
    + _CONSISTENCIA_COLUMNS
    + ["n_dimensoes", "escore", "ranking"]
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


def _eh_verdadeiro(serie: pd.Series) -> pd.Series:
    """True so onde o valor e verdadeiro; nulo/NaN/qualquer outra coisa = False
    (mesma regra de `dashboard.core.periodo._eh_fixado`)."""
    return serie.map(lambda v: False if pd.isna(v) else bool(v)).astype(bool)


def _formato_por_tipo(tipo: pd.Series) -> pd.Series:
    """`Tipo` da Silver (FEED/REELS) -> formato (reel = 1, post = 0)."""
    return (tipo.astype(str).str.strip().str.upper() == "REELS").astype("int64")


def _resultado_insuficiente(n_publicacoes: int, n_dias: int) -> dict:
    return {
        "taxa_mensal": float("nan"),
        "ic_inferior": float("nan"),
        "ic_superior": float("nan"),
        "n_publicacoes": int(n_publicacoes),
        "n_dias": int(n_dias),
        "confiavel": False,
        "estado": TENDENCIA_DADOS_INSUFICIENTES,
    }


def preparar_publicacoes(
    df_publicacoes: pd.DataFrame, now: pd.Timestamp
) -> pd.DataFrame:
    """Aplica as regras de unidade da ADR 0047 as publicacoes de UM perfil e
    devolve o DataFrame pronto para a regressao (`engajamento`, `formato`,
    `data_hora` UTC naive), ja:

    - deduplicado por `id` (um reel tambem aparece no scraper de posts;
      a linha de reel, `formato == 1`, e a preferida); linhas sem `id` sao
      mantidas (nao ha como saber se repetem);
    - sem publicacoes fixadas (`isPinned` verdadeiro; nulo/ausente = nao
      fixada, ADR 0041);
    - so com publicacoes com pelo menos `MIN_DIAS_DE_VIDA` dias em `now`.

    `formato` (reel = 1, post = 0) vem da coluna `formato` se existir; senao de
    `Tipo` (REELS = 1); senao 0 para todas."""
    colunas = ["likesCount", "commentsCount", "data_hora"]
    opcionais = ["id", "isPinned", "Tipo", "formato"]
    working = df_publicacoes.reindex(
        columns=colunas + [c for c in opcionais if c in df_publicacoes.columns]
    ).copy()

    if "formato" in working.columns:
        working["formato"] = (
            pd.to_numeric(working["formato"], errors="coerce").fillna(0) > 0
        ).astype("int64")
    elif "Tipo" in working.columns:
        working["formato"] = _formato_por_tipo(working["Tipo"])
    else:
        working["formato"] = 0

    if "isPinned" in working.columns:
        working = working[~_eh_verdadeiro(working["isPinned"])]

    if "id" in working.columns:
        # Reel primeiro: em empate de `id`, a linha de reel e a que fica.
        working = working.sort_values("formato", ascending=False, kind="stable")
        working = pd.concat(
            [
                working[working["id"].isna()],
                working[working["id"].notna()].drop_duplicates(subset="id"),
            ]
        )

    # `data_hora` pode chegar tz-aware: normaliza para UTC naive (comparavel a `now`).
    working["data_hora"] = pd.to_datetime(
        working["data_hora"], errors="coerce", utc=True
    ).dt.tz_localize(None)
    working = working.dropna(subset=["data_hora"])
    working["engajamento"] = pd.to_numeric(
        working["likesCount"], errors="coerce"
    ).fillna(0) + pd.to_numeric(working["commentsCount"], errors="coerce").fillna(0)

    now = pd.Timestamp(now)
    if now.tzinfo is not None:
        now = now.tz_convert("UTC").tz_localize(None)
    working = working[working["data_hora"] <= now - pd.Timedelta(days=MIN_DIAS_DE_VIDA)]
    return (
        working[["engajamento", "formato", "data_hora"]]
        .sort_values("data_hora", kind="stable")
        .reset_index(drop=True)
    )


def classificar_tendencia(
    taxa_mensal: float, ic_inferior: float, ic_superior: float, confiavel: bool
) -> str:
    """Estado da Tendencia (verbete do CONTEXT.md): "Dados insuficientes" se
    nao confiavel; "Subindo" se o IC fica todo acima de zero E a taxa >=
    `MIN_EFEITO_MENSAL`; "Caindo" se o IC fica todo abaixo de zero E a taxa <=
    -`MIN_EFEITO_MENSAL`; "Estável" caso contrario."""
    if not confiavel or any(
        pd.isna(v) for v in (taxa_mensal, ic_inferior, ic_superior)
    ):
        return TENDENCIA_DADOS_INSUFICIENTES
    if ic_inferior > 0 and taxa_mensal >= MIN_EFEITO_MENSAL:
        return TENDENCIA_SUBINDO
    if ic_superior < 0 and taxa_mensal <= -MIN_EFEITO_MENSAL:
        return TENDENCIA_CAINDO
    return TENDENCIA_ESTAVEL


def estimar_tendencia_engajamento(
    df_publicacoes: pd.DataFrame, now: pd.Timestamp | None = None
) -> dict:
    """Taxa mensal de variacao do engajamento por publicacao de UM perfil
    (ADR 0047): regressao por publicacao ("OLS com controles" da ficha
    `docs/modelagens/tendencia.md`).

    `df_publicacoes`: publicacoes do perfil (reels e/ou posts, concatenados)
    com `likesCount`, `commentsCount`, `data_hora`; opcionalmente `id`,
    `isPinned`, `Tipo` ou `formato` -- ver `preparar_publicacoes`, que aplica
    dedup, exclusao de fixadas e maturidade. `now`: data de referencia
    (default: agora, UTC).

    Modelo: `log(max(curtidas + comentarios, 1)) ~ 1 + t [+ formato]`, com
    `t` = dias desde a primeira publicacao do perfil / `DIAS_POR_MES` e
    `formato` (reel = 1, post = 0) como controle so quando o perfil tem os
    dois formatos. Seguidores ficam fora (constantes no perfil).
    `taxa_mensal = exp(beta_t) - 1`; IC de 95% = `exp(limites) - 1`.

    Retorna um dict com `taxa_mensal`, `ic_inferior`, `ic_superior`,
    `n_publicacoes`, `n_dias` (dias distintos com publicacao), `confiavel`
    (>= `MIN_PUBLICACOES` publicacoes em >= `MIN_DIAS_DISTINTOS` dias) e
    `estado` (um de `ESTADOS_TENDENCIA`). Sem confiabilidade, taxa e IC sao
    `NaN` e o estado e "Dados insuficientes". Nunca levanta excecao por falta
    de dado."""
    if now is None:
        now = pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))
    if df_publicacoes is None or df_publicacoes.empty:
        return _resultado_insuficiente(0, 0)

    pub = preparar_publicacoes(df_publicacoes, now)
    n_publicacoes = len(pub)
    n_dias = int(pub["data_hora"].dt.normalize().nunique()) if n_publicacoes else 0
    if n_publicacoes < MIN_PUBLICACOES or n_dias < MIN_DIAS_DISTINTOS:
        return _resultado_insuficiente(n_publicacoes, n_dias)

    t = (
        (pub["data_hora"] - pub["data_hora"].min()).dt.total_seconds()
        / 86400.0
        / DIAS_POR_MES
    ).to_numpy(dtype="float64")
    y = np.log(np.clip(pub["engajamento"].to_numpy(dtype="float64"), 1.0, None))
    colunas = [np.ones(n_publicacoes), t]
    if pub["formato"].nunique() > 1:
        colunas.append(pub["formato"].to_numpy(dtype="float64"))
    x = np.column_stack(colunas)

    ajuste = sm.OLS(y, x).fit()
    beta = float(ajuste.params[1])
    limite_inferior, limite_superior = (
        float(v) for v in np.asarray(ajuste.conf_int(alpha=1 - NIVEL_CONFIANCA))[1]
    )
    if not all(math.isfinite(v) for v in (beta, limite_inferior, limite_superior)):
        # Desenho degenerado (ex.: formato colinear com o tempo): sem
        # estimativa util, trata como dado insuficiente.
        return _resultado_insuficiente(n_publicacoes, n_dias)

    taxa = math.expm1(beta)
    ic_inferior = math.expm1(limite_inferior)
    ic_superior = math.expm1(limite_superior)
    return {
        "taxa_mensal": taxa,
        "ic_inferior": ic_inferior,
        "ic_superior": ic_superior,
        "n_publicacoes": int(n_publicacoes),
        "n_dias": n_dias,
        "confiavel": True,
        "estado": classificar_tendencia(taxa, ic_inferior, ic_superior, True),
    }


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

        # Publicacoes para a Consistencia (ADR 0047): reels (formato 1) e
        # posts de feed (formato 0, ou 1 quando `Tipo == "REELS"`). Dedup por
        # `id`, fixadas e maturidade ficam em `preparar_publicacoes`, por perfil.
        colunas_pub = _POST_COLUMNS + _POST_OPTIONAL_COLUMNS
        posts_pub = df_posts.reindex(columns=colunas_pub)
        posts_pub = posts_pub.assign(formato=_formato_por_tipo(posts_pub["Tipo"]))
        todos = pd.concat(
            [df_reels.reindex(columns=colunas_pub).assign(formato=1), posts_pub],
            ignore_index=True,
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

            tendencia = estimar_tendencia_engajamento(
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
                    "consistencia": tendencia["taxa_mensal"],
                    "consistencia_taxa_mensal": tendencia["taxa_mensal"],
                    "consistencia_ic_inferior": tendencia["ic_inferior"],
                    "consistencia_ic_superior": tendencia["ic_superior"],
                    "consistencia_n_publicacoes": tendencia["n_publicacoes"],
                    "consistencia_n_dias": tendencia["n_dias"],
                    "tendencia_engajamento": tendencia["estado"],
                }
            )

        out = pd.DataFrame(
            linhas,
            columns=["inputUrl", "username", *DIMENSOES, *_CONSISTENCIA_COLUMNS],
        )
        for dim in DIMENSOES:
            out[dim] = out[dim].astype("float64")
            out[f"{dim}_norm"] = min_max_normalize(out[dim])
        for col in (
            "consistencia_taxa_mensal",
            "consistencia_ic_inferior",
            "consistencia_ic_superior",
        ):
            out[col] = out[col].astype("float64")
        for col in ("consistencia_n_publicacoes", "consistencia_n_dias"):
            out[col] = out[col].fillna(0).astype("int64")
        out["tendencia_engajamento"] = (
            out["tendencia_engajamento"]
            .fillna(TENDENCIA_DADOS_INSUFICIENTES)
            .astype("string")
        )

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
