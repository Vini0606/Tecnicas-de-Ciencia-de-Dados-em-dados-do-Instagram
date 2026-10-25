"""Tendência de um indicador do próprio governador ao longo do tempo (ADR 0040
/ issue #285).

**RASCUNHO PROVISÓRIO.** O método e todos os limiares abaixo vêm das
simulações dos notebooks `tendencia_01`/`tendencia_02` (ver
`docs/modelagens/tendencia.md`) e AINDA NÃO foram validados com dado real: o
backtest com a Coleta de 90 dias (#284/#256) é quem decide. Nada aqui deve ser
lido como método validado.

Funções puras (DataFrame in, dataclass out), sem Streamlit. A série é sempre a
BRUTA por data de publicação de UM governador -- nunca o índice 0-100
normalizado entre perfis --, então a Tendência de um governador não depende
dos demais (só a versão "Todos" combina perfis, via `tendencia_conjunto`).

Método (candidatos da ficha de modelagem):
- valor/contagem: OLS de `log(valor)` no tempo, formato como controle, IC t;
- proporção: OLS de `log((k + 0,5) / (n + 1))`, formato como controle;
- "Todos": mediana das tendências individuais, cada perfil pesando igual, IC
  por bootstrap de perfis.

Unidade de tempo: períodos de 90 dias (`PERIODO_DIAS`, como no notebook
`tendencia_02`: o tempo da regressão é `dias / 90`). A estimativa é, portanto,
a variação relativa POR PERÍODO DE 90 DIAS, em escala log, e NÃO a variação
ponta a ponta da janela: duas séries com a mesma inclinação dão a mesma
variação mesmo que cubram janelas de tamanhos diferentes. Para janelas bem
mais curtas que 90 dias o número é uma extrapolação da inclinação observada.

A série de comentários usa a data de PUBLICAÇÃO da postagem comentada (ADR
0040), ligada pelo `id_reel` da Gold de sentimento ao `id` de `reels_clean`/
`posts_clean` (ver `serie_positividade_por_publicacao`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SUBINDO = "Subindo"
CAINDO = "Caindo"
ESTAVEL = "Estável"
INSUFICIENTE = "Dados insuficientes"
ESTADOS = (SUBINDO, CAINDO, ESTAVEL, INSUFICIENTE)

# Unidade de tempo da regressão: períodos de 90 dias (igual ao notebook
# tendencia_02; é a unidade em que a variação é expressa, não um limiar).
PERIODO_DIAS = 90

# --- Limiares: TODOS provisórios --------------------------------------------
# PROVISÓRIO (ADR 0040, aguarda #284): efeito mínimo (fração do nível do próprio
# perfil) para virar Subindo/Caindo. Faixa a testar no backtest: 2% a 10%.
MIN_EFEITO = 0.05
# PROVISÓRIO (ADR 0040, aguarda #284): mínimo de observações (linhas válidas da
# série) para classificar. Faixa a testar no backtest: 10 a 20.
MIN_OBSERVACOES = 10
# PROVISÓRIO (ADR 0040, aguarda #284): mínimo de dias distintos com dado. Faixa
# a testar no backtest: 8 a 15.
MIN_DIAS_DISTINTOS = 8
# PROVISÓRIO (ADR 0040, aguarda #284): nível de confiança do intervalo.
NIVEL_CONFIANCA = 0.95
# PROVISÓRIO (ADR 0040, aguarda #284): mínimo de perfis com estimativa para a
# visão "Todos" (a ficha não fixa este número; escolha de rascunho).
MIN_PERFIS_CONJUNTO = 5
# PROVISÓRIO (ADR 0040, aguarda #284): repetições do bootstrap de perfis e
# semente fixa (resultado determinístico para a mesma entrada).
N_BOOTSTRAP = 1000
SEMENTE_BOOTSTRAP = 20261012
# PROVISÓRIO (ADR 0040, aguarda #284): abaixo desta fração de comentários
# ligados a uma data de publicação, a legenda avisa que a cobertura é baixa.
LIMIAR_COBERTURA_BAIXA = 0.9


@dataclass(frozen=True)
class Tendencia:
    """Resultado de uma Tendência. `variacao`/`ic_*` são frações relativas
    (0,12 = +12%) POR PERÍODO DE 90 DIAS (`PERIODO_DIAS`); `None` em "Dados
    insuficientes". `estimativa_log` guarda a estimativa em escala log (usada
    pela agregação). `n_perfis` só é preenchido na versão "Todos"."""

    estado: str
    variacao: float | None = None
    ic_inferior: float | None = None
    ic_superior: float | None = None
    estimativa_log: float | None = None
    n_observacoes: int = 0
    n_dias: int = 0
    n_perfis: int | None = None


def _insuficiente(
    n_obs: int = 0, n_dias: int = 0, n_perfis: int | None = None
) -> Tendencia:
    """Resultado "Dados insuficientes" (sem seta nem número), guardando as
    contagens para a interface explicar o porquê."""
    return Tendencia(
        INSUFICIENTE, n_observacoes=n_obs, n_dias=n_dias, n_perfis=n_perfis
    )


def _classificar(est_log: float, lo_log: float, hi_log: float) -> str:
    """Estado a partir da estimativa e do IC (escala log): Subindo/Caindo só
    se o IC exclui zero E a variação passa de `MIN_EFEITO`; senão Estável."""
    est, lo, hi = np.expm1([est_log, lo_log, hi_log])
    if lo > 0 and est >= MIN_EFEITO:
        return SUBINDO
    if hi < 0 and est <= -MIN_EFEITO:
        return CAINDO
    return ESTAVEL


def _montar(est_log: float, lo_log: float, hi_log: float, **extra) -> Tendencia:
    """Converte estimativa e IC de escala log para variação relativa e
    classifica."""
    est, lo, hi = (float(v) for v in np.expm1([est_log, lo_log, hi_log]))
    return Tendencia(
        _classificar(est_log, lo_log, hi_log),
        variacao=est,
        ic_inferior=lo,
        ic_superior=hi,
        estimativa_log=float(est_log),
        **extra,
    )


def _t_critico(graus: int) -> float:
    """Valor crítico t bicaudal para `NIVEL_CONFIANCA` (mín. 1 grau)."""
    from scipy import stats

    return float(stats.t.ppf(0.5 + NIVEL_CONFIANCA / 2, max(graus, 1)))


def _ajustar(
    dias: pd.Series, y: np.ndarray, formato: pd.Series | None
) -> Tendencia | None:
    """OLS de `y` em t (dias desde o primeiro dia da série / `PERIODO_DIAS`,
    ou seja, em períodos de 90 dias) + dummies de formato; o coeficiente de t é
    a variação (log) por período de 90 dias. `None` se o ajuste não for possível (sem variação no tempo, sem graus de
    liberdade ou matriz singular)."""
    amplitude = float(dias.max() - dias.min())
    if amplitude <= 0:
        return None
    t = ((dias - dias.min()) / PERIODO_DIAS).to_numpy(dtype=float)
    colunas = [np.ones(len(t)), t]
    if formato is not None and formato.nunique() > 1:
        dummies = pd.get_dummies(formato, drop_first=True, dtype=float)
        colunas.extend(dummies[c].to_numpy() for c in dummies.columns)
    x = np.column_stack(colunas)
    gl = len(y) - x.shape[1]
    if gl < 1:
        return None
    try:
        inv = np.linalg.inv(x.T @ x)
    except np.linalg.LinAlgError:
        return None
    beta = inv @ x.T @ y
    residuo = y - x @ beta
    s2 = float(residuo @ residuo) / gl
    erro = float(np.sqrt(max(s2 * inv[1, 1], 0.0)))
    crit = _t_critico(gl)
    return _montar(
        beta[1],
        beta[1] - crit * erro,
        beta[1] + crit * erro,
        n_observacoes=len(y),
        n_dias=int(dias.nunique()),
    )


def _preparar(df: pd.DataFrame, colunas: list[str], coluna_data: str):
    """Cópia de `df` com `_data` (datetime) e sem datas inválidas; `None` se
    vazio ou sem as colunas exigidas."""
    if df.empty or not set(colunas).issubset(df.columns):
        return None
    base = df.copy()
    base["_data"] = pd.to_datetime(base[coluna_data], errors="coerce")
    return base.dropna(subset=["_data"])


def _dias(serie: pd.Series) -> pd.Series:
    """Dias inteiros desde a primeira data da série (sem fuso, dia normalizado)."""
    dt = serie.dt.tz_localize(None) if serie.dt.tz is not None else serie
    return (dt.dt.normalize() - dt.dt.normalize().min()).dt.days


def _finalizar(
    base: pd.DataFrame, y: pd.Series, coluna_formato: str | None
) -> Tendencia:
    """Aplica os mínimos (`MIN_OBSERVACOES` linhas válidas, `MIN_DIAS_DISTINTOS`
    dias distintos) e ajusta. Cada linha de `base` conta como UMA observação:
    quem chama deve entregar uma linha por publicação."""
    n_obs = len(base)
    dias = _dias(base["_data"])
    n_dias = int(dias.nunique())
    if n_obs < MIN_OBSERVACOES or n_dias < MIN_DIAS_DISTINTOS:
        return _insuficiente(n_obs, n_dias)
    formato = (
        base[coluna_formato].fillna("?").astype(str)
        if coluna_formato and coluna_formato in base.columns
        else None
    )
    resultado = _ajustar(dias, y.to_numpy(dtype=float), formato)
    return resultado or _insuficiente(n_obs, n_dias)


def tendencia_valor(
    df: pd.DataFrame,
    coluna_data: str = "data",
    coluna_valor: str = "valor",
    coluna_formato: str | None = None,
) -> Tendencia:
    """Tendência de um indicador de valor/contagem (uma linha por publicação
    ou por dia) de UM governador. Valores nulos, não numéricos ou <= 0 (o log
    não existe) e datas inválidas são descartados antes de contar o mínimo de
    observações. Nunca lança exceção: série vazia/sem coluna -> Dados
    insuficientes."""
    base = _preparar(df, [coluna_data, coluna_valor], coluna_data)
    if base is None:
        return _insuficiente()
    base = base.assign(_valor=pd.to_numeric(base[coluna_valor], errors="coerce"))
    base = base[base["_valor"] > 0]
    if base.empty:
        return _insuficiente()
    return _finalizar(base, np.log(base["_valor"]), coluna_formato)


def tendencia_proporcao(
    df: pd.DataFrame,
    coluna_data: str = "data",
    coluna_positivos: str = "positivos",
    coluna_total: str = "total",
    coluna_formato: str | None = None,
) -> Tendencia:
    """Tendência de uma proporção (positivos/total) de UM governador, com
    correção de continuidade `log((k + 0,5) / (n + 1))` por observação.

    NÃO é ponderada pelo nº de comentários (n). Decisão baseada no notebook
    `notebooks/modelagens/tendencia_02_proporcoes_e_agregacao.ipynb`: o OLS do
    log da proporção sem peso foi o único candidato calibrado (falso alarme
    4,9%, cobertura do IC 94,7%); a regressão logística ponderada por n ficou
    descalibrada (falso alarme 25,8%, cobertura 74,2%). Limitação conhecida,
    a testar no backtest (#284): dias/publicações com poucos comentários pesam
    igual aos de muitos comentários, então proporções ruidosas (n pequeno)
    influenciam a reta tanto quanto as estáveis. Linhas com total <= 0, nulos ou positivos fora de [0, total] são
    descartadas."""
    base = _preparar(df, [coluna_data, coluna_positivos, coluna_total], coluna_data)
    if base is None:
        return _insuficiente()
    k = pd.to_numeric(base[coluna_positivos], errors="coerce")
    n = pd.to_numeric(base[coluna_total], errors="coerce")
    valido = k.notna() & n.notna() & (n > 0) & (k >= 0) & (k <= n)
    base, k, n = base[valido], k[valido], n[valido]
    if base.empty:
        return _insuficiente()
    return _finalizar(base, np.log((k + 0.5) / (n + 1.0)), coluna_formato)


def tendencia_conjunto(tendencias: list[Tendencia]) -> Tendencia:
    """Tendência de "Todos": MEDIANA das estimativas individuais (escala log),
    cada perfil pesando igual -- nunca soma bruta --, com IC por bootstrap de
    perfis (semente fixa). Perfis em "Dados insuficientes" ficam de fora; com
    menos de `MIN_PERFIS_CONJUNTO` perfis com estimativa, "Dados
    insuficientes"."""
    estimativas = np.array(
        [t.estimativa_log for t in tendencias if t.estimativa_log is not None],
        dtype=float,
    )
    if len(estimativas) < MIN_PERFIS_CONJUNTO:
        return _insuficiente(n_perfis=len(estimativas))
    rng = np.random.default_rng(SEMENTE_BOOTSTRAP)
    indices = rng.integers(0, len(estimativas), size=(N_BOOTSTRAP, len(estimativas)))
    medianas = np.median(estimativas[indices], axis=1)
    alfa = (1 - NIVEL_CONFIANCA) / 2
    lo, hi = np.quantile(medianas, [alfa, 1 - alfa])
    return _montar(
        float(np.median(estimativas)),
        float(lo),
        float(hi),
        n_observacoes=sum(t.n_observacoes for t in tendencias),
        n_dias=0,
        n_perfis=len(estimativas),
    )


# --- Série de positividade dos comentários (data de PUBLICAÇÃO) --------------

COLUNAS_SERIE = ["chave", "id_publicacao", "data", "formato", "positivos", "total"]


@dataclass(frozen=True)
class SeriePublicacao:
    """Série de comentários por publicação e a cobertura do join.

    `serie`: uma linha por (perfil, publicação, formato) com `data` = data de
    PUBLICAÇÃO da postagem comentada, `positivos` e `total` de comentários.
    `taxa_correspondencia`: fração dos comentários ligados a uma publicação com
    data (`None` se não havia comentários); os demais ficam FORA da série,
    sem usar a data do comentário como alternativa."""

    serie: pd.DataFrame
    taxa_correspondencia: float | None
    n_comentarios: int = 0
    n_correspondidos: int = 0


def _datas_publicacao(publicacoes: pd.DataFrame) -> pd.DataFrame | None:
    """`id_publicacao` (str) e `data` (dia, sem fuso) de reels_clean/posts_clean;
    `None` se faltar `id`/`data_hora`. Ids repetidos ficam com a primeira linha."""
    if publicacoes.empty or not {"id", "data_hora"}.issubset(publicacoes.columns):
        return None
    datas = pd.to_datetime(publicacoes["data_hora"], errors="coerce")
    if datas.dt.tz is not None:
        datas = datas.dt.tz_localize(None)
    tabela = pd.DataFrame(
        {
            "id_publicacao": publicacoes["id"].astype(str),
            "data": datas.dt.normalize(),
        }
    ).dropna(subset=["data"])
    return tabela.drop_duplicates(subset="id_publicacao", keep="first")


def serie_positividade_por_publicacao(
    comentarios: pd.DataFrame, reels: pd.DataFrame, posts: pd.DataFrame
) -> SeriePublicacao:
    """Série BRUTA de positividade dos comentários por publicação comentada.

    `comentarios`: comentários da Gold de sentimento já com a coluna `chave`
    (perfil normalizado) e `id_reel` (id da publicação comentada, issue #212),
    `origem_comentario` (reel/post) e `sentiment_label`. `reels`/`posts`:
    `reels_clean`/`posts_clean` (`id`, `data_hora`). O join é `id_reel` -> `id`
    na tabela escolhida por `origem_comentario` (o mesmo id pode existir nas
    duas tabelas), e a data é a de PUBLICAÇÃO (ADR 0040). Comentários sem
    publicação correspondente (ou origem desconhecida) ficam fora; a
    cobertura volta em `taxa_correspondencia`. `id_comment` repetido conta uma
    vez. Nunca usa o índice 0-100 do NSM."""
    vazia = pd.DataFrame(columns=COLUNAS_SERIE)
    exigidas = {"chave", "id_reel", "origem_comentario", "sentiment_label"}
    if comentarios.empty or not exigidas.issubset(comentarios.columns):
        return SeriePublicacao(vazia, None)
    df = comentarios
    if "id_comment" in df.columns:
        df = df.drop_duplicates(subset=["id_comment"], keep="first")
    n_comentarios = len(df)
    origem = df["origem_comentario"].astype(str).str.strip().str.lower()
    partes = []
    for formato, publicacoes in (("reel", reels), ("post", posts)):
        datas = _datas_publicacao(publicacoes)
        if datas is None:
            continue
        sub = df[origem == formato]
        ligados = pd.DataFrame(
            {
                "chave": sub["chave"].to_numpy(),
                "id_publicacao": sub["id_reel"].astype(str).to_numpy(),
                "positivo": (sub["sentiment_label"] == "positive")
                .astype(int)
                .to_numpy(),
            }
        ).merge(datas, on="id_publicacao", how="inner")
        partes.append(ligados.assign(formato=formato))
    base = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    n_correspondidos = len(base)
    taxa = n_correspondidos / n_comentarios if n_comentarios else None
    if base.empty:
        return SeriePublicacao(vazia, taxa, n_comentarios, 0)
    agregado = (
        base.groupby(["chave", "id_publicacao", "data", "formato"])["positivo"]
        .agg(positivos="sum", total="size")
        .reset_index()
    )
    return SeriePublicacao(
        agregado[COLUNAS_SERIE], taxa, n_comentarios, n_correspondidos
    )


def tendencia_positividade_comentarios(
    serie: pd.DataFrame, chave_selecionada: str | None
) -> Tendencia:
    """Tendência da proporção de comentários positivos (ADR 0040, PROVISÓRIO)
    sobre a `serie` de `serie_positividade_por_publicacao`. Governador
    selecionado: só a série dele (os outros perfis não entram, logo não a
    alteram). `None` ("Todos"): mediana das tendências de cada perfil, peso
    igual por perfil. Cada linha da série é uma publicação (a observação do
    mínimo de `MIN_OBSERVACOES`); os dias distintos são dias de publicação."""

    def _de(perfil: pd.DataFrame) -> Tendencia:
        return tendencia_proporcao(
            perfil,
            coluna_positivos="positivos",
            coluna_total="total",
            coluna_formato="formato",
        )

    if chave_selecionada is None:
        return tendencia_conjunto([_de(g) for _, g in serie.groupby("chave")])
    return _de(serie[serie["chave"] == chave_selecionada])
