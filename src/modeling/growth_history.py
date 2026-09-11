"""
CMGR (crescimento mensal composto) e retenção sobre o histórico acumulado
(ADR 0020, Ficha 7 / issue #92).

Lê `governor_engagement_history` (crescimento de audiência) e
`governor_sentiment_history` (retenção de sentimento positivo do público)
-- ambas tabelas append já existentes e independentes desta issue (ver ADR
0016 e issue #52). Este módulo só CALCULA sobre o que já foi acumulado; não
altera como as tabelas de histórico são populadas, e não depende de nenhum
outro estágio pós-modelagem (NSM/Score ICE, ADR 0020 Fichas 5/6) -- por
isso vive fora de `src/modeling/orchestration.py` (ver
`scripts/run_growth_metrics.py`).

*** LIMITAÇÃO EXPLÍCITA (declarar sempre que este módulo for consumido) ***
Em 2026-09 o pipeline acumulou poucas execuções de modelagem. CMGR e
retenção aqui calculados são, portanto, ILUSTRATIVOS -- validam a fórmula e
o formato de saída, não sustentam conclusões definitivas sobre o
crescimento real dos perfis monitorados no Cap. 6/7 do TCC. O campo
`confiavel` (`False` sempre que `n_periodos < MIN_PERIODS_CONFIAVEL`, ver
`compute_cmgr`/`compute_retention`) sinaliza isso explicitamente para
qualquer consumidor (dashboard, texto do TCC). Essa marca não é um bug a
corrigir: ela só troca de valor conforme mais execuções reais do pipeline
se acumularem ao longo do tempo de operação, não com mais código.

Convenção de "não calculável": as funções deste módulo NUNCA levantam erro
para histórico curto -- retornam `float("nan")` (não `None`), seguindo a
mesma convenção já usada para `r2_holdout` em
`src/modeling/post_performance.py` (ADR 0019), o que permite escrever o
resultado direto numa coluna `float64` nullable do Gold sem conversão
adicional. O motivo de um `nan` fica sempre em `motivo`.
"""

from __future__ import annotations

import math

import pandas as pd

# Limiar arbitrário e documentado -- ainda não há operação real longa o
# bastante para calibrar este número por dados observados; 6
# meses/execuções (meio ano de acompanhamento) é uma escolha didática até
# existir base real para revisão. Ver limitação no topo do módulo.
MIN_PERIODS_CONFIAVEL = 6

GROUP_COL_DEFAULT = "inputUrl"
DATE_COL_DEFAULT = "_generated_at"
PERIOD_COL = "periodo"

MOTIVO_HISTORICO_INSUFICIENTE = "historico_insuficiente"
MOTIVO_PERIODO_ZERO = "periodo_zero"
MOTIVO_VALOR_INICIAL_INVALIDO = "valor_inicial_invalido"
MOTIVO_VALOR_ANTERIOR_INVALIDO = "valor_anterior_invalido"


def _to_month_period(series: pd.Series) -> pd.Series:
    """`_generated_at` chega tz-aware (UTC) das tabelas Gold reais, mas
    `Series.dt.to_period` não aceita timezone -- normaliza para naive antes
    de truncar a granularidade mensal (a hora do dia não importa aqui)."""
    parsed = pd.to_datetime(series, utc=True).dt.tz_localize(None)
    return parsed.dt.to_period("M")


def aggregate_monthly(
    df: pd.DataFrame,
    value_col: str,
    group_col: str = GROUP_COL_DEFAULT,
    date_col: str = DATE_COL_DEFAULT,
    agg: str = "last",
) -> pd.DataFrame:
    """Reduz um histórico append (uma linha por execução) a uma linha por
    grupo (perfil) por mês-calendário.

    `agg="last"` para métricas de estoque/snapshot (ex.: `followersCount`,
    onde a última execução do mês já reflete as anteriores); `agg="mean"`
    para métricas já proporcionais/comparáveis entre execuções (ex.: share
    de sentimento positivo).
    """
    colunas_saida = [group_col, PERIOD_COL, value_col]
    if df.empty:
        return pd.DataFrame(columns=colunas_saida)

    working = df[[group_col, date_col, value_col]].dropna(subset=[group_col, date_col]).copy()
    if working.empty:
        return pd.DataFrame(columns=colunas_saida)

    working[PERIOD_COL] = _to_month_period(working[date_col])

    grouped = working.groupby([group_col, PERIOD_COL], as_index=False)[value_col].agg(agg)
    return grouped.sort_values([group_col, PERIOD_COL]).reset_index(drop=True)


def positive_share_monthly(
    df_sentiment_history: pd.DataFrame,
    group_col: str = GROUP_COL_DEFAULT,
    date_col: str = DATE_COL_DEFAULT,
    label_col: str = "sentiment_label",
    positive_label: str = "positive",
) -> pd.DataFrame:
    """Reduz o histórico de sentimento (uma linha por comentário/legenda/
    transcrição por execução) a uma série mensal de share de sentimento
    positivo por perfil -- insumo de `compute_retention` para a métrica de
    retenção de sentimento (Ficha 7). `positive_label` é comparado
    case-sensitive; normalize a coluna antes de chamar esta função se a
    fonte gravar rótulos em outra capitalização."""
    colunas_saida = [group_col, PERIOD_COL, "positive_share"]
    if df_sentiment_history.empty:
        return pd.DataFrame(columns=colunas_saida)

    working = df_sentiment_history[[group_col, date_col, label_col]].dropna(
        subset=[group_col, date_col]
    ).copy()
    if working.empty:
        return pd.DataFrame(columns=colunas_saida)

    working[PERIOD_COL] = _to_month_period(working[date_col])
    working["_is_positive"] = (working[label_col] == positive_label).astype(float)

    grouped = (
        working.groupby([group_col, PERIOD_COL], as_index=False)["_is_positive"]
        .mean()
        .rename(columns={"_is_positive": "positive_share"})
    )
    return grouped.sort_values([group_col, PERIOD_COL]).reset_index(drop=True)


def compute_cmgr(
    df_monthly: pd.DataFrame,
    value_col: str,
    group_col: str = GROUP_COL_DEFAULT,
    min_periods_confiavel: int = MIN_PERIODS_CONFIAVEL,
) -> pd.DataFrame:
    """CMGR por grupo: `(valor_final / valor_inicial) ** (1 / n_meses) - 1`,
    sobre a série mensal já agregada por `aggregate_monthly`.

    Retorna sempre uma linha por grupo -- nunca levanta erro para histórico
    curto. Quando o cálculo não é possível, `cmgr` é `nan` e o motivo fica
    em `motivo` (`historico_insuficiente`: menos de 2 execuções mensais;
    `periodo_zero`: primeira e última execução no mesmo mês;
    `valor_inicial_invalido`: valor inicial <= 0, divisão indefinida).

    `confiavel` é `False` sempre que `n_periodos < min_periods_confiavel`
    (ver limitação documentada no topo do módulo), mesmo quando o CMGR foi
    calculável -- histórico curto não deixa de ser ilustrativo só porque a
    fórmula rodou sem erro.
    """
    linhas = []
    for group_value, group_df in df_monthly.groupby(group_col):
        group_df = group_df.sort_values(PERIOD_COL)
        n_periodos = len(group_df)
        valor_inicial = group_df[value_col].iloc[0]
        valor_final = group_df[value_col].iloc[-1]

        cmgr = float("nan")
        motivo = None

        if n_periodos < 2:
            motivo = MOTIVO_HISTORICO_INSUFICIENTE
        else:
            n_meses = (group_df[PERIOD_COL].iloc[-1] - group_df[PERIOD_COL].iloc[0]).n
            if n_meses <= 0:
                motivo = MOTIVO_PERIODO_ZERO
            elif valor_inicial is None or pd.isna(valor_inicial) or valor_inicial <= 0:
                motivo = MOTIVO_VALOR_INICIAL_INVALIDO
            else:
                cmgr = (valor_final / valor_inicial) ** (1.0 / n_meses) - 1.0

        confiavel = not math.isnan(cmgr) and n_periodos >= min_periods_confiavel

        linhas.append(
            {
                group_col: group_value,
                "valor_inicial": valor_inicial,
                "valor_final": valor_final,
                "n_periodos": n_periodos,
                "cmgr": cmgr,
                "confiavel": confiavel,
                "motivo": motivo,
            }
        )

    return pd.DataFrame(linhas)


def compute_retention(
    df_monthly: pd.DataFrame,
    value_col: str,
    group_col: str = GROUP_COL_DEFAULT,
    min_periods_confiavel: int = MIN_PERIODS_CONFIAVEL,
) -> pd.DataFrame:
    """Taxa média de retenção por grupo: média de `valor_t / valor_(t-1)`
    (capada em 1.0) entre meses consecutivos da série mensal já agregada
    por `aggregate_monthly`/`positive_share_monthly`.

    1.0 = manteve 100% (ou mais) do valor do mês anterior; abaixo de 1.0 =
    perdeu parte do valor anterior. É deliberadamente uma medida de
    "quanto do período anterior foi mantido", não de crescimento -- por
    isso capada em 1.0 (ver `test_compute_retention_capa_crescimento_em_100_por_cento`);
    CMGR já cobre a magnitude de crescimento.

    Pares com `valor_(t-1) == 0` (ou nulo) são ignorados (razão
    indefinida) e não contam em `n_pares_validos`. Nunca levanta erro para
    histórico curto: com menos de 2 execuções mensais ou nenhum par
    válido, `retencao_media` é `nan` e o motivo fica em `motivo`.

    Mesma semântica de `confiavel` de `compute_cmgr` -- ver limitação
    documentada no topo do módulo.
    """
    linhas = []
    for group_value, group_df in df_monthly.groupby(group_col):
        group_df = group_df.sort_values(PERIOD_COL)
        n_periodos = len(group_df)
        valores = group_df[value_col].tolist()

        ratios = [
            min(atual / anterior, 1.0)
            for anterior, atual in zip(valores, valores[1:])
            if anterior is not None and not pd.isna(anterior) and anterior > 0
        ]

        retencao_media = float("nan")
        motivo = None
        if n_periodos < 2:
            motivo = MOTIVO_HISTORICO_INSUFICIENTE
        elif not ratios:
            motivo = MOTIVO_VALOR_ANTERIOR_INVALIDO
        else:
            retencao_media = sum(ratios) / len(ratios)

        confiavel = not math.isnan(retencao_media) and n_periodos >= min_periods_confiavel

        linhas.append(
            {
                group_col: group_value,
                "n_periodos": n_periodos,
                "n_pares_validos": len(ratios),
                "retencao_media": retencao_media,
                "confiavel": confiavel,
                "motivo": motivo,
            }
        )

    return pd.DataFrame(linhas)


def compute_growth_metrics(
    df_engagement_history: pd.DataFrame,
    df_sentiment_history: pd.DataFrame,
    group_col: str = GROUP_COL_DEFAULT,
    min_periods_confiavel: int = MIN_PERIODS_CONFIAVEL,
) -> pd.DataFrame:
    """Combina CMGR de audiência (`followersCount`, de
    `governor_engagement_history`) com retenção de sentimento positivo (de
    `governor_sentiment_history`) numa linha por perfil -- saída consumida
    por `scripts/run_growth_metrics.py` / `ModelEnricher.write_growth_metrics`.

    `ilustrativo` é `True` sempre que qualquer uma das duas métricas não
    for `confiavel` -- ver limitação documentada no topo do módulo. `nota`
    carrega a ressalva textual pronta para exibição (dashboard/TCC).
    """
    df_engagement_monthly = aggregate_monthly(
        df_engagement_history, value_col="followersCount", group_col=group_col, agg="last"
    )
    df_cmgr = compute_cmgr(
        df_engagement_monthly,
        value_col="followersCount",
        group_col=group_col,
        min_periods_confiavel=min_periods_confiavel,
    ).rename(
        columns={
            "n_periodos": "cmgr_n_periodos",
            "confiavel": "cmgr_confiavel",
            "motivo": "cmgr_motivo",
        }
    )

    df_sentiment_monthly = positive_share_monthly(df_sentiment_history, group_col=group_col)
    df_retencao = compute_retention(
        df_sentiment_monthly,
        value_col="positive_share",
        group_col=group_col,
        min_periods_confiavel=min_periods_confiavel,
    ).rename(
        columns={
            "retencao_media": "retencao",
            "n_periodos": "retencao_n_periodos",
            "n_pares_validos": "retencao_n_pares_validos",
            "confiavel": "retencao_confiavel",
            "motivo": "retencao_motivo",
        }
    )

    combined = pd.merge(df_cmgr, df_retencao, on=group_col, how="outer")
    combined["cmgr_confiavel"] = combined["cmgr_confiavel"].fillna(False)
    combined["retencao_confiavel"] = combined["retencao_confiavel"].fillna(False)
    combined["ilustrativo"] = ~(combined["cmgr_confiavel"] & combined["retencao_confiavel"])
    combined["nota"] = (
        "CMGR/retencao ilustrativos: poucas execucoes de modelagem acumuladas ate o "
        "momento (ver ADR 0020, Ficha 7). Nao usar como conclusao definitiva de "
        "crescimento -- reavaliar conforme mais execucoes reais do pipeline se "
        "acumularem."
    )
    return combined
