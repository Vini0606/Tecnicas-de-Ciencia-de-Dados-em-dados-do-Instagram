"""Analise de clusters de reels com sentimento -- secao da Tela "Comparar
perfis" (issue #189, spec #182).

Substitui a antiga secao "Governadores do grupo ...". Funcoes puras (testadas
em `tests/test_dashboard_screens_comparar_clusters.py`); a renderizacao
Streamlit fica em `render_clusters()` e so orquestra I/O sobre elas.

Decisoes:

- **Dado real, numero real de clusters.** Os botoes saem de
  `governor_clusters_reels` (hoje 2 clusters); os 3 clusters do prototipo vem
  do Cap. 5 do TCC e NAO sao reproduzidos. Nada aqui assume um numero fixo.
- **Numeracao por tamanho.** "Cluster 1" e o MAIOR, "Cluster 2" o seguinte, etc.
  (o id bruto do pipeline nunca aparece). O ruido do DBSCAN (`-1`) vira
  "Casos atipicos / virais", fora da numeracao.
- **Nome/descricao/recomendacao por regra**, comparando mediana do cluster
  com a mediana GLOBAL dos reels (limiares nomeados abaixo). Texto sempre
  associativo, nunca causal.
- **Escopo.** Metricas e sentimento sao do cluster no conjunto dos perfis;
  so a contagem de `contagem_governador` e do governador selecionado.
- Engajamento por reel = curtidas + comentarios (Silver). O escore PC1 nao
  existe no Gold, entao nao e usado.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.core import data

RUIDO = -1
NOME_RUIDO = "Casos atípicos / virais"

# Abaixo disso o cluster exibe o aviso "poucos reels -- nao generalize".
LIMIAR_POUCOS_REELS = 5

# Razao (mediana do cluster / mediana global) a partir da qual a duracao ou o
# engajamento contam como "acima"/"abaixo" e como "muito acima"/"muito abaixo".
# Pontos de partida redondos e explicaveis; nao calibrados contra dado real.
RAZAO_ACIMA = 1.15
RAZAO_ABAIXO = 0.85
RAZAO_MUITO_ACIMA = 1.5
RAZAO_MUITO_ABAIXO = 0.5

# Diferenca (pontos percentuais) de % negativo vs. o global a partir da qual o
# sentimento do cluster conta como "mais"/"menos" negativo.
LIMIAR_SENTIMENTO_PP = 5.0

SENTIMENTOS = [
    ("positive", "Positivo"),
    ("neutral", "Neutro"),
    ("negative", "Negativo"),
]

_ENGAJAMENTO_TEXTO = {-2: "muito baixo", -1: "baixo", 0: "médio", 1: "alto", 2: "alto"}
_DURACAO_TEXTO = {
    -2: "muito abaixo da mediana",
    -1: "abaixo da mediana",
    0: "próxima da mediana",
    1: "acima da mediana",
    2: "muito acima da mediana",
}
_ENGAJAMENTO_NOME = {
    -2: "engajamento muito abaixo da mediana",
    -1: "engajamento abaixo da mediana",
    0: "engajamento próximo da mediana",
    1: "engajamento acima da mediana",
    2: "engajamento muito acima da mediana",
}

_COLUNAS_BASE = [
    "id_reel",
    "cluster",
    "inputUrl",
    "duracao",
    "likes",
    "comentarios",
    "views",
    "engajamento",
]


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


# ---------------------------------------------------------------------------
# Base: 1 linha por reel clusterizado, com metricas da Silver
# ---------------------------------------------------------------------------


def montar_base_reels(df_clusters: pd.DataFrame, df_reels: pd.DataFrame) -> pd.DataFrame:
    """Reels da tabela de clusters (filtrada a `content_type == 'reel'` quando a
    coluna existe) unidos por `id_reel` = `id` as metricas da Silver. Reel sem
    linha na Silver permanece (conta no cluster; metricas `NaN`). Vazio, com as
    colunas certas, se nao houver cluster."""
    if df_clusters.empty or not {"id_reel", "cluster_label"}.issubset(df_clusters.columns):
        return pd.DataFrame(columns=_COLUNAS_BASE)
    cl = df_clusters
    if "content_type" in cl.columns:
        cl = cl[cl["content_type"] == "reel"]
    base = pd.DataFrame(
        {"id_reel": cl["id_reel"].astype(str), "cluster": cl["cluster_label"]}
    ).drop_duplicates(subset=["id_reel"])

    metricas = pd.DataFrame(columns=["id_reel", "inputUrl", "duracao", "likes", "comentarios", "views"])
    if not df_reels.empty and "id" in df_reels.columns:

        def col(nome: str) -> pd.Series:
            if nome in df_reels.columns:
                return df_reels[nome]
            return pd.Series([pd.NA] * len(df_reels), index=df_reels.index)

        metricas = pd.DataFrame(
            {
                "id_reel": df_reels["id"].astype(str),
                "inputUrl": col("inputUrl"),
                "duracao": pd.to_numeric(col("videoDuration"), errors="coerce"),
                "likes": pd.to_numeric(col("likesCount"), errors="coerce"),
                "comentarios": pd.to_numeric(col("commentsCount"), errors="coerce"),
                "views": pd.to_numeric(col("videoPlayCount"), errors="coerce"),
            }
        ).drop_duplicates(subset=["id_reel"])
    base = base.merge(metricas, on="id_reel", how="left")
    base["engajamento"] = base["likes"].add(base["comentarios"])
    return base[_COLUNAS_BASE].reset_index(drop=True)


def ordenar_clusters(base: pd.DataFrame) -> list[int]:
    """Ids de cluster do maior para o menor (empate: id menor primeiro). O
    ruido entra na ordenacao por tamanho como qualquer outro."""
    if base.empty:
        return []
    tamanhos = base.groupby("cluster").size()
    ordenado = sorted(tamanhos.items(), key=lambda kv: (-kv[1], kv[0]))
    return [int(c) for c, _ in ordenado]


def rotulo_botao(cluster_id: int, ordem: list[int], nome: str) -> str:
    """"Cluster N -- <nome>" (N = posicao por tamanho entre os clusters nao
    ruido); o ruido vira so "Casos atipicos / virais", nunca "-1"."""
    if cluster_id == RUIDO:
        return NOME_RUIDO
    return f"{numero_cluster(cluster_id, ordem)} — {nome}"


def numero_cluster(cluster_id: int, ordem: list[int]) -> str:
    """"Cluster N" por tamanho, ignorando o ruido na numeracao."""
    if cluster_id == RUIDO:
        return NOME_RUIDO
    posicoes = [c for c in ordem if c != RUIDO]
    return f"Cluster {posicoes.index(cluster_id) + 1}"


# ---------------------------------------------------------------------------
# Metricas por cluster
# ---------------------------------------------------------------------------


def medianas_globais(base: pd.DataFrame) -> dict[str, float | None]:
    """Mediana de duracao e engajamento por reel sobre TODOS os reels
    clusterizados -- referencia das regras de nome/engajamento/recomendacao."""

    def mediana(coluna: str) -> float | None:
        if base.empty:
            return None
        v = base[coluna].dropna()
        return float(v.median()) if not v.empty else None

    return {"duracao": mediana("duracao"), "engajamento": mediana("engajamento")}


def metricas_cluster(base: pd.DataFrame, cluster_id: int) -> dict:
    """Os 6 cartoes do cluster (valores reais da Silver) + a mediana de
    duracao/engajamento usada nas regras. `None` onde nao ha dado."""
    sub = base[base["cluster"] == cluster_id] if not base.empty else base

    def media(coluna: str) -> float | None:
        v = sub[coluna].dropna() if not sub.empty else pd.Series(dtype=float)
        return float(v.mean()) if not v.empty else None

    def mediana(coluna: str) -> float | None:
        v = sub[coluna].dropna() if not sub.empty else pd.Series(dtype=float)
        return float(v.median()) if not v.empty else None

    return {
        "n_reels": len(sub),
        "duracao_media": media("duracao"),
        "likes_media": media("likes"),
        "comentarios_media": media("comentarios"),
        "views_media": media("views"),
        "duracao_mediana": mediana("duracao"),
        "engajamento_mediano": mediana("engajamento"),
    }


def nivel_relativo(valor: float | None, referencia: float | None) -> int | None:
    """-2/-1/0/1/2 = muito abaixo/abaixo/proximo/acima/muito acima da
    referencia (razao valor/referencia vs. os limiares nomeados). `None` se
    faltar dado ou a referencia for <= 0."""
    if valor is None or referencia is None or pd.isna(valor) or pd.isna(referencia):
        return None
    if referencia <= 0:
        return None
    razao = valor / referencia
    if razao >= RAZAO_MUITO_ACIMA:
        return 2
    if razao >= RAZAO_ACIMA:
        return 1
    if razao <= RAZAO_MUITO_ABAIXO:
        return -2
    if razao <= RAZAO_ABAIXO:
        return -1
    return 0


def engajamento_qualitativo(metricas: dict, globais: dict) -> str:
    """"muito baixo"/"baixo"/"médio"/"alto" pela posicao frente a mediana geral."""
    nivel = nivel_relativo(metricas["engajamento_mediano"], globais["engajamento"])
    return "sem dado" if nivel is None else _ENGAJAMENTO_TEXTO[nivel]


def fmt_duracao(segundos: float | None) -> tuple[str, str]:
    """("42 s", "~1 min") ou ("—", "") sem dado."""
    if segundos is None or pd.isna(segundos):
        return "—", ""
    minutos = max(1, round(segundos / 60)) if segundos >= 30 else 0
    aprox = f"~{minutos} min" if minutos else "menos de 1 min"
    return f"{segundos:.0f} s", aprox


def fmt_num(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    return f"{valor:,.0f}".replace(",", ".")


# ---------------------------------------------------------------------------
# Nome / descricao / recomendacao por regra
# ---------------------------------------------------------------------------


def nome_cluster(cluster_id: int, metricas: dict, globais: dict) -> str:
    """Nome por regra (duracao e engajamento vs. mediana global). Ruido =
    "Casos atipicos / virais". Sem dado comparavel: "Sem dados suficientes"."""
    if cluster_id == RUIDO:
        return NOME_RUIDO
    dur = nivel_relativo(metricas["duracao_mediana"], globais["duracao"])
    eng = nivel_relativo(metricas["engajamento_mediano"], globais["engajamento"])
    partes = []
    if dur is not None and dur != 0:
        partes.append(f"Duração {_DURACAO_TEXTO[dur]}")
    if eng is not None and eng != 0:
        partes.append(_ENGAJAMENTO_NOME[eng].capitalize() if not partes else _ENGAJAMENTO_NOME[eng])
    if partes:
        return ", ".join(partes)
    if dur is None and eng is None:
        return "Sem dados suficientes"
    return "Perfil típico (próximo da mediana)"


def aviso_poucos_reels(n_reels: int) -> str | None:
    if n_reels < LIMIAR_POUCOS_REELS:
        return f"Poucos reels ({n_reels}) — não generalize."
    return None


def descricao_cluster(
    cluster_id: int, metricas: dict, globais: dict, total_reels: int, nome: str
) -> dict:
    """{"titulo", "subtitulo", "texto"} do cartao de descricao (por regra)."""
    n = metricas["n_reels"]
    pct = f"{n / total_reels * 100:.0f}%" if total_reels else "—"
    dur = nivel_relativo(metricas["duracao_mediana"], globais["duracao"])
    eng = nivel_relativo(metricas["engajamento_mediano"], globais["engajamento"])
    frases = []
    if cluster_id == RUIDO:
        frases.append(
            "Reels que não se encaixam em nenhum grupo — podem ser desempenhos fora do "
            "padrão (virais) ou formatos incomuns."
        )
    if dur is not None:
        frases.append(f"A duração mediana está {_DURACAO_TEXTO[dur]}.")
    if eng is not None:
        frases.append(f"O engajamento por reel (curtidas + comentários) está {_DURACAO_TEXTO[eng]}.")
    if not frases:
        frases.append("Sem dados suficientes de duração e engajamento para descrever este cluster.")
    return {
        "titulo": nome,
        "subtitulo": f"{n} reels ({pct} dos reels clusterizados)",
        "texto": " ".join(frases),
    }


def sentimento_vs_global(composicao: dict | None, global_comp: dict | None) -> int | None:
    """-1/0/1 = cluster menos/igual/mais negativo que o global (pontos
    percentuais, `LIMIAR_SENTIMENTO_PP`). `None` se faltar comentario."""
    if not composicao or not global_comp:
        return None
    diff = composicao["pct"]["negative"] - global_comp["pct"]["negative"]
    if diff >= LIMIAR_SENTIMENTO_PP:
        return 1
    if diff <= -LIMIAR_SENTIMENTO_PP:
        return -1
    return 0


def recomendacao_cluster(
    metricas: dict, globais: dict, composicao: dict | None, global_comp: dict | None
) -> str:
    """"O que fazer com este cluster" -- texto ASSOCIATIVO (nunca causal),
    baseado em duracao/engajamento/sentimento relativos a mediana geral."""
    if metricas["n_reels"] < LIMIAR_POUCOS_REELS:
        return (
            "Amostra pequena: não há base para recomendar. Trate estes reels como "
            "casos isolados e olhe-os individualmente, sem generalizar."
        )
    eng = nivel_relativo(metricas["engajamento_mediano"], globais["engajamento"])
    dur = nivel_relativo(metricas["duracao_mediana"], globais["duracao"])
    partes = []
    if eng is None:
        partes.append("Sem dado de engajamento suficiente para comparar este cluster.")
    elif eng > 0:
        partes.append(
            "Reels deste cluster estão associados a engajamento acima da mediana — "
            "vale tomá-los como referência de formato."
        )
    elif eng < 0:
        partes.append(
            "Reels deste cluster estão associados a engajamento abaixo da mediana — "
            "teste variações de formato antes de repetir este padrão."
        )
    else:
        partes.append("Reels deste cluster têm engajamento próximo da mediana — um formato neutro.")
    if dur is not None and dur != 0:
        sentido = "mais longos" if dur > 0 else "mais curtos"
        partes.append(f"São {sentido} que a mediana, o que pode ser parte do padrão.")
    sent = sentimento_vs_global(composicao, global_comp)
    if sent == 1:
        partes.append("Os comentários tendem a ser mais negativos que o geral — acompanhe a reação.")
    elif sent == -1:
        partes.append("Os comentários tendem a ser menos negativos que o geral.")
    elif sent == 0:
        partes.append("O sentimento dos comentários fica próximo do geral.")
    return " ".join(partes)


# ---------------------------------------------------------------------------
# Sentimento por cluster
# ---------------------------------------------------------------------------


def composicao_sentimento(
    df_comentarios: pd.DataFrame, base: pd.DataFrame, cluster_id: int | None = None
) -> dict | None:
    """Composicao positivo/neutro/negativo (contagem e %) dos comentarios dos
    reels do cluster, ligados por `id_reel`. `cluster_id=None` = todos os reels
    clusterizados (referencia global). Comentario de reel fora do cluster (ou
    sem `id_reel`/reel clusterizado) e ignorado. `None` se nao houver
    comentario."""
    if (
        df_comentarios.empty
        or base.empty
        or not {"id_reel", "sentiment_label"}.issubset(df_comentarios.columns)
    ):
        return None
    reels = base if cluster_id is None else base[base["cluster"] == cluster_id]
    ids = set(reels["id_reel"])
    sel = df_comentarios[df_comentarios["id_reel"].astype(str).isin(ids)]
    sel = sel[sel["sentiment_label"].isin([k for k, _ in SENTIMENTOS])]
    total = len(sel)
    if total == 0:
        return None
    contagem = {k: int((sel["sentiment_label"] == k).sum()) for k, _ in SENTIMENTOS}
    return {
        "total": total,
        "contagem": contagem,
        "pct": {k: v / total * 100 for k, v in contagem.items()},
    }


# ---------------------------------------------------------------------------
# Linha do governador
# ---------------------------------------------------------------------------


def contagem_governador(base: pd.DataFrame, governor_url: str) -> dict:
    """{"total", "por_cluster": {id: n}} dos reels do governador entre os
    clusterizados (casados por `inputUrl` normalizado)."""
    if base.empty or "inputUrl" not in base.columns:
        return {"total": 0, "por_cluster": {}}
    chave = _normalize_url(pd.Series([governor_url])).iloc[0]
    meus = base[base["inputUrl"].notna() & (_normalize_url(base["inputUrl"]) == chave)]
    por_cluster = {int(c): int(n) for c, n in meus.groupby("cluster").size().items()}
    return {"total": len(meus), "por_cluster": por_cluster}


def frase_governador(contagem: dict, ordem: list[int]) -> str:
    """"Dos seus N reels, X estao no Cluster 1 e Y no Cluster 2" (so clusters
    com reels dele); sem reels -> mensagem amigavel."""
    if contagem["total"] == 0:
        return "Este governador não tem reels na clusterização atual."
    partes = [(contagem["por_cluster"][c], numero_cluster(c, ordem)) for c in ordem if c in contagem["por_cluster"]]
    itens = [
        f"{n} {'estão' if n != 1 else 'está'} em {nome}" if i == 0 else f"{n} em {nome}"
        for i, (n, nome) in enumerate(partes)
    ]
    corpo = itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]
    return f"Dos seus {contagem['total']} reels, {corpo}."


# ---------------------------------------------------------------------------
# Visual (tokens claro/escuro; paleta de dado, separada do vermelho IESB)
# ---------------------------------------------------------------------------

# Slots categoricos de cluster (ordem fixa por tamanho) e cores de sentimento
# (status good/critical + cinza neutro) -- variante por tema (skill dataviz).
CORES_CLUSTER = {
    "light": ["#2a78d6", "#eb6834", "#1baf7a", "#9a6ad9"],
    "dark": ["#3987e5", "#d95926", "#199e70", "#a97ee0"],
}
CORES_SENTIMENTO = {
    "light": {"positive": "#0ca30c", "neutral": "#8a8a85", "negative": "#d03b3b"},
    "dark": {"positive": "#0ca30c", "neutral": "#9a9a95", "negative": "#d03b3b"},
}
_COR_EXTRA = {"light": "#8a8a85", "dark": "#9a9a95"}


def cor_cluster(cluster_id: int, ordem: list[int], tema: str = "light") -> str:
    """Cor do cluster pela posicao por tamanho (nao repinta ao filtrar); alem
    dos slots, cinza (nunca matiz gerado)."""
    paleta = CORES_CLUSTER.get(tema, CORES_CLUSTER["light"])
    pos = ordem.index(cluster_id) if cluster_id in ordem else len(paleta)
    return paleta[pos] if pos < len(paleta) else _COR_EXTRA.get(tema, _COR_EXTRA["light"])


def figura_rosca(composicao: dict, tema: str = "light") -> go.Figure:
    cores = CORES_SENTIMENTO.get(tema, CORES_SENTIMENTO["light"])
    nomes = [
        f"{rotulo} — {composicao['contagem'][k]} ({composicao['pct'][k]:.0f}%)" for k, rotulo in SENTIMENTOS
    ]
    fig = go.Figure(
        go.Pie(
            labels=nomes,
            values=[composicao["contagem"][k] for k, _ in SENTIMENTOS],
            hole=0.6,
            sort=False,
            marker={"colors": [cores[k] for k, _ in SENTIMENTOS], "line": {"width": 2}},
            textinfo="none",
            hovertemplate="%{label}<extra></extra>",
        )
    )
    fig.update_layout(
        showlegend=True,
        legend={"orientation": "v", "y": 0.5},
        margin={"t": 10, "b": 10, "l": 10, "r": 10},
        height=260,
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def _tema_atual() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:  # noqa: BLE001
        return "light"


def render_clusters(governor_url: str) -> None:
    """Secao completa; so I/O Streamlit sobre as funcoes puras acima."""
    base = montar_base_reels(data.load_clusters_content(), data.load_reels_content())
    comentarios = data.comments_only(data.load_sentiment())
    tema = _tema_atual()

    st.markdown("#### Clusters de Reels & Sentimento")
    st.caption(
        "Segmentação automática dos reels cruzada com o sentimento dos comentários. "
        "Selecione um cluster para ver suas métricas, sua descrição e a composição de sentimento."
    )
    st.markdown(
        '<span style="border:1px solid #8a8a85;border-radius:8px;padding:2px 10px;'
        'font-size:12px;">agrupamento experimental</span>',
        unsafe_allow_html=True,
    )

    ordem = ordenar_clusters(base)
    if not ordem:
        st.info("Ainda não há clusterização de reels disponível para esta análise.")
        return

    st.write(frase_governador(contagem_governador(base, governor_url), ordem))

    globais = medianas_globais(base)
    por_cluster = {c: metricas_cluster(base, c) for c in ordem}
    nomes = {c: nome_cluster(c, por_cluster[c], globais) for c in ordem}
    escolhido = st.radio(
        "Cluster",
        options=ordem,
        format_func=lambda c: rotulo_botao(c, ordem, nomes[c]),
        horizontal=True,
        key="comparar_cluster_ativo",
        label_visibility="collapsed",
    )
    metricas = por_cluster[escolhido]
    cor = cor_cluster(escolhido, ordem, tema)
    desc = descricao_cluster(escolhido, metricas, globais, len(base), nomes[escolhido])
    aviso = aviso_poucos_reels(metricas["n_reels"])
    st.markdown(
        f'<div style="border-left:6px solid {cor};background:rgba(128,128,128,0.08);'
        f'border-radius:6px;padding:10px 14px;margin:8px 0;">'
        f'<div style="font-weight:600;">{desc["titulo"]}</div>'
        f'<div style="font-size:13px;opacity:0.75;">{desc["subtitulo"]}</div>'
        f'<div style="margin-top:6px;">{desc["texto"]}</div>'
        + (f'<div style="margin-top:6px;font-weight:600;">{aviso}</div>' if aviso else "")
        + "</div>",
        unsafe_allow_html=True,
    )

    seg, aprox = fmt_duracao(metricas["duracao_media"])
    cartoes = [
        ("Reels no cluster", fmt_num(metricas["n_reels"])),
        ("Duração média", f"{seg} ({aprox})" if aprox else seg),
        ("Engajamento", engajamento_qualitativo(metricas, globais)),
        ("Curtidas médias", fmt_num(metricas["likes_media"])),
        ("Comentários médios", fmt_num(metricas["comentarios_media"])),
        ("Views médias", fmt_num(metricas["views_media"])),
    ]
    for linha in (cartoes[:3], cartoes[3:]):
        for col, (rotulo, valor) in zip(st.columns(3), linha, strict=True):
            col.metric(rotulo, valor)

    composicao = composicao_sentimento(comentarios, base, escolhido)
    global_comp = composicao_sentimento(comentarios, base, None)
    st.markdown("**Composição de sentimento dos comentários**")
    if composicao is None:
        st.caption("Este cluster ainda não tem comentários analisados.")
    else:
        st.plotly_chart(figura_rosca(composicao, tema), width="stretch", key="comparar_rosca_cluster")
        st.caption(f"{composicao['total']} comentários dos reels deste cluster.")

    st.markdown("**O que fazer com este cluster**")
    st.info(recomendacao_cluster(metricas, globais, composicao, global_comp))
