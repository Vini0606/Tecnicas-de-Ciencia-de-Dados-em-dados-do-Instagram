"""Tela 4 -- "Comparar perfis" (ADR 0021 / issue #115).

Responde "como estou vs. outros?" -- benchmarking do governador selecionado
contra os pares do mesmo grupo de desempenho (`governor_profile_clusters_engagement`,
Fase 2 / clusterização de PERFIL por engajamento, distinta da clusterização de
CONTEÚDO usada em `produzir.py`). Substitui `pages/04_recommendations.py`
(ADR 0020) -- ver ADR 0021, Cutover. Mesma estrutura fixa das Telas 1/3/6 (ver
`resumo.py`/`radar.py`/`funil.py`): funções puras nomeadas, testadas em
`tests/test_dashboard_screens_comparar.py`; `render()` só orquestra I/O do
Streamlit sobre o resultado dessas funções.

Decisões de implementação registradas aqui (ver PR da issue #115 para o
texto completo, incluindo a tabela real de perfil por cluster que embasa o
mapa de nomes abaixo):

1. **Ambiguidade de spec resolvida -- nome real da coluna de cluster.** A
   issue pede a coluna `cluster_perfil_engajamento` em
   `governor_profile_clusters_engagement`, "confirmada em
   `src/dashboard/recommendations.py`" -- mas essa confirmação era indireta:
   `recommendations.py` recebe `df_profile_clusters` já renomeado por
   `src/dashboard/filters.py::build_profile_cluster_directory` (que está
   sendo descontinuado por esta mesma ADR). A tabela Gold real
   (`GOLD_PROFILE_CLUSTERS_ENGAGEMENT_SCHEMA`, `src/schemas_delta.py`) grava
   a coluna como `cluster_label`, igual à tabela de cluster de CONTEÚDO
   (`GOLD_CLUSTERS_SCHEMA`). `dashboard/core/data.py::load_clusters_profile()`
   devolve a tabela crua (`cluster_label`), então `_carregar_cluster_perfil`
   abaixo faz o mesmo rename que `build_profile_cluster_directory` fazia,
   mas self-contained dentro desta tela (sem importar `src/dashboard/filters.py`
   -- mesmo raciocínio de autocontenção das Telas 1/3/6: cada tela não
   depende de outra tela nem do pacote antigo, que está sendo apagado tela
   por tela).
2. **Mapa curado de nomes de grupo -- `NOMES_GRUPOS_DESEMPENHO`.** Derivado
   da inspeção real das médias de `% ENGAJAMENTO` (usada aqui como
   alcance-proxy -- é literalmente uma das 3 features usadas para gerar o
   próprio clustering, `scripts/run_profile_clustering_engagement.py`,
   `FEATURE_COLUMNS`), `% positivo` (comentários) e `FREQUENCIA` por cluster,
   nos 27 perfis reais (dado gerado localmente para esta issue -- ver PR
   para a tabela completa). O algoritmo vencedor foi DBSCAN (`cluster_score`
   0.55), com 3 grupos reais: `-1` (1 governador, ruído do DBSCAN -- nome
   fixado por `CONTEXT.md`/dicionário de dados: "casos atípicos / virais",
   nunca "-1"), `0` (24/27 governadores -- a MAIOR frequência de postagem e
   o MENOR engajamento relativo dos 3 grupos) e `1` (2 governadores -- o
   MAIOR engajamento e MAIOR % positivo, mas a MENOR frequência, cerca de
   1/3 da do grupo 0). Só 3 clusters reais (não uma escala grande) -- ver
   PR para a tabela completa e a íntegra do raciocínio de cada nome.
3. **Alcance-proxy -- fonte e rótulo.** "Alcance-proxy" = `% ENGAJAMENTO`
   de `governor_engagement` (`load_engagement()`), o mesmo número já
   rotulado "% engajamento" em `resumo.py` -- NUNCA a métrica
   "Visualizações" da Tela 6 (`videoPlayCount`, dado real de Reels, cálculo
   totalmente diferente; ver CONTEXT.md, "Alcance" vs. "Visualizações").
4. **`_peer_urls` -- portado, não apenas chamado.** A lógica de pares
   (mesmo `cluster_perfil_engajamento`, excluindo o próprio) de
   `src/dashboard/recommendations.py::_peer_urls` foi reescrita aqui usando
   o mesmo idioma de normalização de URL (`_normalize_url`/
   `_filtrar_por_governador`) já duplicado em toda tela nova, em vez de
   `select_governor_rows` (`src/dashboard/filters.py`, descontinuado) -- ver
   Cutover desta issue no PR para o que foi portado vs. apagado.
5. **Par de destaque -- maior diferença POSITIVA em qualquer métrica.**
   `_selecionar_par_destaque` varre as 3 métricas comparadas, na ordem de
   `_METRICAS`, e todos os pares, escolhendo a maior diferença
   estritamente positiva (par melhor que o próprio perfil) encontrada --
   nunca inventa um destaque quando nenhum par supera o próprio perfil em
   nada (`None` nesse caso). Empate: primeira ocorrência (ordem de
   `_METRICAS`, depois ordem de `df_pares`) -- determinístico, testado.
6. **Selo "agrupamento experimental" -- sempre visível.** Renderizado logo
   após `stage_label()`, em TODO caminho de `render()` (sem governador
   disponível, sem cluster atribuído, ou fluxo normal) -- nunca condicional
   a dado disponível (issue #115, user story 4: o clustering de perfil
   ainda não foi validado plenamente, então o aviso precisa aparecer mesmo
   quando a tela tem dado bonito para mostrar).
7. **Estado vazio -- `NaN`/ausência de cluster nunca é erro.**
   `_cluster_do_governador` retorna `None` tanto para "sem linha
   correspondente" quanto para "`cluster_perfil_engajamento` é `NaN`" --
   `render()` trata os dois com o mesmo `st.info` amigável (issue #115,
   user story 5), nunca uma exceção não tratada.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.core import data
from dashboard.core.components import decision_band, footnote, stage_label
from dashboard.core.theme import COLORS

_PLACEHOLDER_SEM_GOVERNADOR = "—"
_PLACEHOLDER_SEM_DADO = "—"

_STAGE = "Segmentação da audiência (Flesch)"
_AVISO_EXPERIMENTAL = (
    "Agrupamento experimental -- a segmentação de perfil ainda não foi "
    "validada plenamente contra os 27 perfis reais; não trate os grupos "
    "abaixo como definitivos."
)

# ---------------------------------------------------------------------------
# Mapa curado de nomes de grupo de desempenho (issue #115, conteúdo curado --
# ver docstring do módulo, decisão 2, e o PR desta issue para a tabela
# completa de perfil médio por cluster que embasa cada nome). NUNCA exibir o
# id numérico bruto ao usuário -- ver `_nome_grupo`.
#
# `-1` é ruído do DBSCAN, não um grupo de negócio -- nome fixado por
# CONTEXT.md/dicionário de dados ("casos atípicos / virais"), não uma escolha
# subjetiva desta tela.
# ---------------------------------------------------------------------------
NOMES_GRUPOS_DESEMPENHO: dict[int, str] = {
    -1: "Casos atípicos / virais",
    0: "Alta frequência, engajamento mais baixo",
    1: "Alto engajamento, baixa frequência",
}
_NOME_GRUPO_PADRAO = "grupo ainda não descrito"

# Abaixo de que |diff_pct| (%) uma métrica conta como "na média dos pares",
# em vez de "acima"/"abaixo" -- ponto de partida documentado (mesmo
# raciocínio de `LIMIAR_NEGATIVIDADE_ALERTA` em `core/deltas.py`: redondo,
# fácil de explicar, não calibrado contra dado real ainda).
LIMIAR_NA_MEDIA_PCT = 1.0

# Fonte única das 3 métricas comparadas (ordem = ordem de exibição e de
# desempate em `_selecionar_par_destaque`).
_METRICAS = [
    {"chave": "alcance_proxy", "rotulo": "Alcance (estimado por engajamento)", "tipo": "pct"},
    {"chave": "pct_positivo", "rotulo": "% positivo", "tipo": "pct"},
    {"chave": "frequencia", "rotulo": "Frequência de postagem", "tipo": "num"},
]


# ---------------------------------------------------------------------------
# Normalização / seleção de governador (duplicado de `resumo.py`/`produzir.py`/
# `radar.py`/`funil.py` -- mesmo raciocínio: cada tela fica autocontida, sem
# depender de outra tela nem de `src/dashboard/filters.py`, que está sendo
# descontinuado tela por tela pela ADR 0021).
# ---------------------------------------------------------------------------


def _normalize_url(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.split("?", n=1)
        .str[0]
        .str.split("#", n=1)
        .str[0]
        .str.rstrip("/")
        .str.lower()
    )


def _governor_options(df_metadata: pd.DataFrame) -> dict[str, str]:
    if df_metadata.empty or "inputUrl" not in df_metadata.columns:
        return {}
    col_nome = "nome" if "nome" in df_metadata.columns else "inputUrl"
    pares = (
        df_metadata[["inputUrl", col_nome]]
        .dropna(subset=["inputUrl"])
        .drop_duplicates(subset=["inputUrl"])
    )
    nomes = pares[col_nome].fillna(pares["inputUrl"])
    return dict(sorted(zip(nomes, pares["inputUrl"], strict=True), key=lambda kv: kv[0]))


def _filtrar_por_governador(
    df: pd.DataFrame, governor_url: str, url_col: str = "inputUrl"
) -> pd.DataFrame:
    if df.empty or url_col not in df.columns:
        return df.iloc[0:0]
    chave = _normalize_url(pd.Series([governor_url])).iloc[0]
    return df[_normalize_url(df[url_col]) == chave]


# ---------------------------------------------------------------------------
# Formatação (arredondamento no ponto de exibição)
# ---------------------------------------------------------------------------


def _fmt_valor_metrica(valor: float | None, tipo: str) -> str:
    if valor is None or pd.isna(valor):
        return _PLACEHOLDER_SEM_DADO
    if tipo == "pct":
        return f"{valor * 100:.1f}%"
    return f"{valor:.1f}"


# ---------------------------------------------------------------------------
# Grupo de desempenho (cluster de perfil) -- ver docstring do módulo,
# decisões 1-2.
# ---------------------------------------------------------------------------


def _carregar_cluster_perfil(df_clusters_profile_raw: pd.DataFrame) -> pd.DataFrame:
    """`governor_profile_clusters_engagement` crua (coluna `cluster_label`,
    ver `GOLD_PROFILE_CLUSTERS_ENGAGEMENT_SCHEMA`) -> `cluster_perfil_engajamento`
    (nome de produto usado por esta tela e, antes, por
    `src/dashboard/recommendations.py`) -- ver docstring do módulo, decisão
    1. `DataFrame` vazio com as colunas certas (nunca exceção) se a tabela
    ainda não existir ou não tiver as colunas esperadas."""
    colunas = ["inputUrl", "cluster_perfil_engajamento"]
    if df_clusters_profile_raw.empty or "inputUrl" not in df_clusters_profile_raw.columns:
        return pd.DataFrame(columns=colunas)
    if "cluster_label" not in df_clusters_profile_raw.columns:
        return pd.DataFrame(columns=colunas)
    return df_clusters_profile_raw[["inputUrl", "cluster_label"]].rename(
        columns={"cluster_label": "cluster_perfil_engajamento"}
    )


def _cluster_do_governador(df_profile_clusters: pd.DataFrame, governor_url: str) -> object | None:
    """Id bruto do cluster de perfil do governador selecionado -- NUNCA
    exibido cru ao usuário (ver `_nome_grupo`). `None` (nunca exceção) se o
    governador não tiver linha correspondente OU se `cluster_perfil_engajamento`
    for `NaN`/ausente -- os dois casos são "sem grupo atribuído" para
    `render()` (issue #115, user story 5)."""
    if df_profile_clusters.empty or "cluster_perfil_engajamento" not in df_profile_clusters.columns:
        return None
    linha = _filtrar_por_governador(df_profile_clusters, governor_url)
    if linha.empty:
        return None
    cluster = linha["cluster_perfil_engajamento"].iloc[0]
    return None if pd.isna(cluster) else cluster


def _nome_grupo(cluster_id: object | None) -> str:
    """Nome funcional de negócio para `cluster_id`, via `NOMES_GRUPOS_DESEMPENHO`
    -- nunca o id numérico bruto (issue #115, user story 1). `_NOME_GRUPO_PADRAO`
    (defensivo, nunca deveria disparar com os 3 clusters reais atuais) se
    `cluster_id` for `None` ou um id ainda não curado -- ver docstring do
    módulo, decisão 2, para o alerta se a escala de clusters mudar."""
    if cluster_id is None:
        return _NOME_GRUPO_PADRAO
    try:
        chave = int(cluster_id)
    except (TypeError, ValueError):
        return _NOME_GRUPO_PADRAO
    return NOMES_GRUPOS_DESEMPENHO.get(chave, _NOME_GRUPO_PADRAO)


def _peer_urls(df_profile_clusters: pd.DataFrame, governor_url: str) -> list[str] | None:
    """`inputUrl` dos pares de cluster de perfil do governador (mesmo
    `cluster_perfil_engajamento`, excluindo o próprio) -- PORTADO (não só
    chamado) de `src/dashboard/recommendations.py::_peer_urls`, reescrito
    com o idioma de normalização de URL já usado nesta tela em vez de
    `select_governor_rows` (`src/dashboard/filters.py`, descontinuado). `None`
    se o governador não tiver cluster atribuído ou não tiver nenhum par."""
    cluster_governador = _cluster_do_governador(df_profile_clusters, governor_url)
    if cluster_governador is None:
        return None

    mesmo_cluster = df_profile_clusters[
        df_profile_clusters["cluster_perfil_engajamento"] == cluster_governador
    ]
    chave_propria = _normalize_url(pd.Series([governor_url])).iloc[0]
    pares = mesmo_cluster[_normalize_url(mesmo_cluster["inputUrl"]) != chave_propria]
    urls = pares["inputUrl"].dropna().unique().tolist()
    return urls or None


# ---------------------------------------------------------------------------
# Métricas por governador (alcance-proxy / % positivo / frequência) -- une
# `governor_engagement`, comentários e `governors_metadata` por `inputUrl`
# normalizado.
# ---------------------------------------------------------------------------


def _montar_metricas_por_governador(
    df_engagement: pd.DataFrame,
    df_sentiment_comentarios: pd.DataFrame,
    df_metadata: pd.DataFrame,
) -> pd.DataFrame:
    """1 linha por governador (`inputUrl` de `df_engagement`): `alcance_proxy`
    (= `% ENGAJAMENTO`), `frequencia` (= `FREQUENCIA`), ambos de
    `df_engagement`; `pct_positivo` (proporção de `sentiment_label ==
    'positive'` em `df_sentiment_comentarios` -- já esperado filtrado a
    comentários pelo chamador via `data.comments_only()`, ver `render()`);
    `nome` de `df_metadata` (`inputUrl` cru como fallback). Junta as 3
    fontes por `inputUrl` NORMALIZADO (mesmo cuidado do resto do dashboard --
    duas tabelas do mesmo pipeline não têm garantia formal de gravar a mesma
    URL byte-a-byte). `DataFrame` vazio (colunas certas, nunca exceção) se
    `df_engagement` estiver vazio ou sem `inputUrl`."""
    colunas = ["inputUrl", "nome", "alcance_proxy", "pct_positivo", "frequencia"]
    if df_engagement.empty or "inputUrl" not in df_engagement.columns:
        return pd.DataFrame(columns=colunas)

    base = df_engagement[["inputUrl"]].dropna().drop_duplicates().copy()
    base["_match_key"] = _normalize_url(base["inputUrl"])

    eng = df_engagement.copy()
    eng["_match_key"] = _normalize_url(eng["inputUrl"])
    for col in ("% ENGAJAMENTO", "FREQUENCIA"):
        if col not in eng.columns:
            eng[col] = pd.NA
    base = base.merge(
        eng[["_match_key", "% ENGAJAMENTO", "FREQUENCIA"]].drop_duplicates(subset=["_match_key"]),
        on="_match_key",
        how="left",
    )

    if (
        not df_sentiment_comentarios.empty
        and "sentiment_label" in df_sentiment_comentarios.columns
        and "inputUrl" in df_sentiment_comentarios.columns
    ):
        sent = df_sentiment_comentarios.copy()
        sent["_match_key"] = _normalize_url(sent["inputUrl"])
        pct_positivo = (
            sent.groupby("_match_key")["sentiment_label"]
            .apply(lambda s: (s == "positive").mean())
            .rename("pct_positivo")
            .reset_index()
        )
        base = base.merge(pct_positivo, on="_match_key", how="left")
    else:
        base["pct_positivo"] = pd.NA

    if (
        not df_metadata.empty
        and "inputUrl" in df_metadata.columns
        and "nome" in df_metadata.columns
    ):
        meta = df_metadata.copy()
        meta["_match_key"] = _normalize_url(meta["inputUrl"])
        base = base.merge(
            meta[["_match_key", "nome"]].drop_duplicates(subset=["_match_key"]),
            on="_match_key",
            how="left",
        )
    else:
        base["nome"] = pd.NA

    base = base.rename(columns={"% ENGAJAMENTO": "alcance_proxy", "FREQUENCIA": "frequencia"})
    base["nome"] = base["nome"].fillna(base["inputUrl"])
    return base[colunas]


# ---------------------------------------------------------------------------
# Barras comparativas (perfil vs. média dos pares) -- issue #115, Testing
# Decisions: função pura, testada com Series/DataFrame sintéticos.
# ---------------------------------------------------------------------------


def _pct_diff_vs_peers(valor_proprio: float | None, valores_pares: pd.Series) -> float | None:
    """% de diferença entre `valor_proprio` e a média de `valores_pares`
    (positivo = próprio maior que a média dos pares) -- PORTADO de
    `src/dashboard/recommendations.py::_pct_diff_vs_peers`. `None` se
    `valor_proprio` for ausente/`NaN`, se não houver par com valor válido,
    ou se a média dos pares for <= 0 (divisão sem sentido)."""
    if valor_proprio is None or pd.isna(valor_proprio):
        return None
    valores_validos = pd.to_numeric(valores_pares, errors="coerce").dropna()
    if valores_validos.empty:
        return None
    media_pares = valores_validos.mean()
    if media_pares <= 0:
        return None
    return (valor_proprio - media_pares) / media_pares * 100


def _rotulo_vs_pares(diff_pct: float | None, limiar_pct: float = LIMIAR_NA_MEDIA_PCT) -> str:
    if diff_pct is None or pd.isna(diff_pct):
        return "sem pares suficientes para comparar"
    if diff_pct > limiar_pct:
        return "acima da média dos pares"
    if diff_pct < -limiar_pct:
        return "abaixo da média dos pares"
    return "na média dos pares"


def _calcular_barra_comparativa(
    chave: str,
    rotulo: str,
    tipo: str,
    valor_proprio: float | None,
    valores_pares: pd.Series,
) -> dict:
    """Barra comparativa perfil vs. média dos pares para 1 métrica -- função
    pura (issue #115, Testing Decisions), testada com `Series` sintética em
    `tests/test_dashboard_screens_comparar.py`."""
    valores_validos = pd.to_numeric(valores_pares, errors="coerce").dropna()
    media_pares = float(valores_validos.mean()) if not valores_validos.empty else None
    diff_pct = _pct_diff_vs_peers(valor_proprio, valores_pares)
    return {
        "chave": chave,
        "rotulo": rotulo,
        "tipo": tipo,
        "valor_proprio": valor_proprio,
        "media_pares": media_pares,
        "diff_pct": diff_pct,
        "rotulo_vs_pares": _rotulo_vs_pares(diff_pct),
    }


def _montar_barras_comparativas(
    valores_proprio: dict[str, float | None], valores_pares: dict[str, pd.Series]
) -> list[dict]:
    return [
        _calcular_barra_comparativa(
            m["chave"],
            m["rotulo"],
            m["tipo"],
            valores_proprio.get(m["chave"]),
            valores_pares.get(m["chave"], pd.Series(dtype=float)),
        )
        for m in _METRICAS
    ]


# ---------------------------------------------------------------------------
# Par de destaque -- issue #115, user story 3 / Testing Decisions.
# ---------------------------------------------------------------------------


def _selecionar_par_destaque(
    df_pares: pd.DataFrame, valores_proprio: dict[str, float | None]
) -> dict | None:
    """Par (governador do mesmo grupo) com a maior diferença POSITIVA em
    qualquer uma das métricas comparadas (issue #115, user story 3) --
    função pura, testada com `DataFrame` sintético. `df_pares` = 1 linha por
    par, colunas `inputUrl`/`nome` + uma coluna por chave de `_METRICAS`
    (`alcance_proxy`/`pct_positivo`/`frequencia`). Desempate determinístico:
    primeira ocorrência na ordem de `_METRICAS`, depois na ordem das linhas
    de `df_pares`. `None` (nunca inventa destaque) se não houver par, ou se
    nenhum par superar o próprio perfil em nenhuma métrica com dado válido."""
    if df_pares.empty:
        return None

    melhor: dict | None = None
    melhor_diff = 0.0
    for m in _METRICAS:
        chave = m["chave"]
        valor_proprio = valores_proprio.get(chave)
        if valor_proprio is None or pd.isna(valor_proprio) or chave not in df_pares.columns:
            continue
        for _, linha in df_pares.iterrows():
            valor_par = linha[chave]
            if pd.isna(valor_par):
                continue
            diff = valor_par - valor_proprio
            if diff > melhor_diff:
                melhor_diff = diff
                nome_par = linha["nome"] if pd.notna(linha.get("nome")) else linha["inputUrl"]
                melhor = {
                    "inputUrl": linha["inputUrl"],
                    "nome": nome_par,
                    "metrica": chave,
                    "rotulo_metrica": m["rotulo"],
                    "tipo": m["tipo"],
                    "valor_par": valor_par,
                    "valor_proprio": valor_proprio,
                    "diff": diff,
                }
    return melhor


def _frase_destaque(destaque: dict | None) -> str:
    if destaque is None:
        return "Nenhum par do mesmo grupo se destaca em alguma métrica no momento."
    valor_par_fmt = _fmt_valor_metrica(destaque["valor_par"], destaque["tipo"])
    rotulo_metrica = destaque["rotulo_metrica"].lower()
    return (
        f"{destaque['nome']} se destaca em {rotulo_metrica}: {valor_par_fmt} -- "
        "estude o conteúdo dele/dela."
    )


# ---------------------------------------------------------------------------
# Faixa de decisão -- issue #115, princípio de design (resposta -> porquê ->
# prova).
# ---------------------------------------------------------------------------


def _barra_mais_destacada(barras: list[dict]) -> dict | None:
    candidatas = [b for b in barras if b["diff_pct"] is not None and not pd.isna(b["diff_pct"])]
    if not candidatas:
        return None
    return max(candidatas, key=lambda b: abs(b["diff_pct"]))


def _nivel_decisao(barras: list[dict]) -> str:
    """Nível da faixa de decisão, a partir da métrica de maior `|diff_pct|`
    entre as 3 comparadas: `"good"` se essa métrica estiver acima dos pares,
    `"warn"` se abaixo, `"info"` se nenhuma tiver diferença acima de
    `LIMIAR_NA_MEDIA_PCT` (ou dado insuficiente para qualquer uma) --
    `"danger"` nunca é usado nesta tela (comparação, não crise; crise já tem
    tela própria, Radar de crise)."""
    barra = _barra_mais_destacada(barras)
    if barra is None or abs(barra["diff_pct"]) <= LIMIAR_NA_MEDIA_PCT:
        return "info"
    return "good" if barra["diff_pct"] > 0 else "warn"


def _frase_decisao(nome_grupo: str, barras: list[dict]) -> str:
    barra = _barra_mais_destacada(barras)
    if barra is None:
        return (
            f'Seu perfil está no grupo "{nome_grupo}" -- ainda não há pares com dado '
            "válido suficiente para comparar."
        )
    if abs(barra["diff_pct"]) <= LIMIAR_NA_MEDIA_PCT:
        return f'Seu perfil está no grupo "{nome_grupo}" -- na média dos pares nas métricas comparadas.'
    return (
        f'Seu perfil está no grupo "{nome_grupo}" -- você está {barra["rotulo_vs_pares"]} '
        f'em {barra["rotulo"].lower()}.'
    )


# ---------------------------------------------------------------------------
# Renderização das barras + tabela de pares
# ---------------------------------------------------------------------------


def _largura_barra_pct(valor: float | None, valor_maximo: float) -> float:
    if valor is None or pd.isna(valor) or valor_maximo <= 0 or valor <= 0:
        return 0.0
    return min(100.0, max(2.0, (valor / valor_maximo) * 100.0))


def _render_barras_comparativas(barras: list[dict]) -> None:
    for barra in barras:
        valores_validos = [
            v for v in (barra["valor_proprio"], barra["media_pares"]) if v is not None and not pd.isna(v)
        ]
        maximo = max(valores_validos) if valores_validos else 0.0
        largura_proprio = _largura_barra_pct(barra["valor_proprio"], maximo)
        largura_pares = _largura_barra_pct(barra["media_pares"], maximo)
        st.markdown(
            f"""
            <div style="margin:14px 0;">
              <div style="font-size:13px;margin-bottom:4px;">
                <strong>{barra["rotulo"]}</strong> -- {barra["rotulo_vs_pares"]}
              </div>
              <div style="font-size:11px;color:{COLORS["muted"]};margin-bottom:2px;">
                Você: {_fmt_valor_metrica(barra["valor_proprio"], barra["tipo"])}
              </div>
              <div style="background:#EEECE3;border-radius:6px;height:16px;width:100%;">
                <div style="background:{COLORS["info"]["fg"]};width:{largura_proprio:.1f}%;
                            height:16px;border-radius:6px;"></div>
              </div>
              <div style="font-size:11px;color:{COLORS["muted"]};margin:6px 0 2px;">
                Média dos pares: {_fmt_valor_metrica(barra["media_pares"], barra["tipo"])}
              </div>
              <div style="background:#EEECE3;border-radius:6px;height:16px;width:100%;">
                <div style="background:{COLORS["muted"]};width:{largura_pares:.1f}%;
                            height:16px;border-radius:6px;"></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _tabela_pares(df_pares: pd.DataFrame) -> pd.DataFrame:
    colunas_saida = ["Governador", "Alcance-proxy", "% positivo", "Frequência"]
    if df_pares.empty:
        return pd.DataFrame(columns=colunas_saida)
    return pd.DataFrame(
        {
            "Governador": df_pares["nome"].fillna(df_pares["inputUrl"]),
            "Alcance-proxy": df_pares["alcance_proxy"].apply(lambda v: _fmt_valor_metrica(v, "pct")),
            "% positivo": df_pares["pct_positivo"].apply(lambda v: _fmt_valor_metrica(v, "pct")),
            "Frequência": df_pares["frequencia"].apply(lambda v: _fmt_valor_metrica(v, "num")),
        }
    ).reset_index(drop=True)


# ---------------------------------------------------------------------------
# render()
# ---------------------------------------------------------------------------


def render() -> None:
    df_metadata = data.load_governors_metadata()
    df_engagement = data.load_engagement()

    options = _governor_options(df_metadata)
    if not options and not df_engagement.empty and "inputUrl" in df_engagement.columns:
        urls = df_engagement["inputUrl"].dropna().unique().tolist()
        options = {url: url for url in urls}

    if not options:
        st.selectbox("Governador", options=[_PLACEHOLDER_SEM_GOVERNADOR], disabled=True)
        stage_label(_STAGE)
        st.caption(_AVISO_EXPERIMENTAL)
        st.info(
            "Nenhum governador disponível ainda -- rode a pipeline "
            "(`uv run python pipeline.py`) para popular o dashboard."
        )
        footnote()
        return

    nome_selecionado = st.selectbox("Governador", options=list(options.keys()))
    governor_url = options[nome_selecionado]
    stage_label(_STAGE)
    st.caption(_AVISO_EXPERIMENTAL)

    # ---- Grupo de desempenho ----
    df_cluster_perfil = _carregar_cluster_perfil(data.load_clusters_profile())
    cluster_governador = _cluster_do_governador(df_cluster_perfil, governor_url)

    if cluster_governador is None:
        st.info(
            "Este governador ainda não tem um grupo de desempenho atribuído -- "
            "rode `uv run python scripts/run_profile_clustering_engagement.py` "
            "para gerar a segmentação de perfil."
        )
        footnote()
        return

    nome_grupo = _nome_grupo(cluster_governador)
    pares_urls = _peer_urls(df_cluster_perfil, governor_url) or []

    # ---- Métricas (alcance-proxy / % positivo / frequência) ----
    df_sentiment_comentarios = data.comments_only(data.load_sentiment())
    df_metricas = _montar_metricas_por_governador(df_engagement, df_sentiment_comentarios, df_metadata)

    chave_propria = _normalize_url(pd.Series([governor_url])).iloc[0]
    linha_propria = df_metricas[_normalize_url(df_metricas["inputUrl"]) == chave_propria]
    valores_proprio = {
        "alcance_proxy": linha_propria["alcance_proxy"].iloc[0] if not linha_propria.empty else None,
        "pct_positivo": linha_propria["pct_positivo"].iloc[0] if not linha_propria.empty else None,
        "frequencia": linha_propria["frequencia"].iloc[0] if not linha_propria.empty else None,
    }

    chaves_pares = set(_normalize_url(pd.Series(pares_urls))) if pares_urls else set()
    df_pares_metricas = df_metricas[_normalize_url(df_metricas["inputUrl"]).isin(chaves_pares)]

    valores_pares_series = {
        "alcance_proxy": df_pares_metricas["alcance_proxy"],
        "pct_positivo": df_pares_metricas["pct_positivo"],
        "frequencia": df_pares_metricas["frequencia"],
    }

    barras = _montar_barras_comparativas(valores_proprio, valores_pares_series)
    destaque = _selecionar_par_destaque(df_pares_metricas, valores_proprio)

    # ---- Frase de decisão ----
    nivel = _nivel_decisao(barras)
    decision_band(_frase_decisao(nome_grupo, barras), level=nivel)

    # ---- Barras comparativas ----
    st.markdown("#### Seu perfil vs. média dos pares do grupo")
    if not pares_urls:
        st.caption(
            "Nenhum outro governador está no mesmo grupo de desempenho ainda -- "
            "sem pares para comparar."
        )
    else:
        _render_barras_comparativas(barras)
        st.caption(
            '"Alcance-proxy" é uma estimativa baseada em engajamento (curtidas + '
            "respostas), não visualizações reais -- ver Funil de engajamento para "
            "visualizações reais dos Reels."
        )

    # ---- Pares do grupo ----
    st.markdown(f'#### Governadores do grupo "{nome_grupo}"')
    if not pares_urls:
        st.caption("Nenhum outro governador no mesmo grupo.")
    else:
        st.write(_frase_destaque(destaque))
        st.dataframe(_tabela_pares(df_pares_metricas), hide_index=True, width="stretch")

    footnote()
