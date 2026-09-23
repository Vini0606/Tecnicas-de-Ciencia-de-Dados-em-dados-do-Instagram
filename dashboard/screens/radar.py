"""Tela 3 -- "Radar de crise" (ADR 0021 / issue #113).

Responde "tem alguma coisa pegando fogo agora?" direto de `governor_sentiment`
/ `governor_sentiment_history`: frase de decisão semafórica -> linha do tempo
de % de comentários negativos -> lista dos comentários negativos mais
recentes do tema em maior ascensão -> rodapé. Mesma estrutura fixa das Telas
1/2 (ver `dashboard/screens/resumo.py`/`produzir.py`, ADR 0021 -- Princípio de
design). Toda a lógica de decisão vive em funções puras nomeadas abaixo,
testadas em `tests/test_dashboard_screens_radar.py` -- `render()` só
orquestra I/O do Streamlit sobre o resultado dessas funções, nunca calcula
nada sozinho (mesmo padrão das duas telas anteriores).

Decisões de implementação registradas aqui (ver PR da issue #113 para o
texto completo):

1. **Limiar de alerta -- fonte única.** `dashboard.core.deltas` já define
   `LIMIAR_NEGATIVIDADE_ALERTA = 0.30` E `resumo.py` (issue #111) já importa
   dali para a própria faixa vermelha -- ou seja, a "fonte única de verdade"
   pedida pela issue #113 já existia antes desta issue rodar (issue #111 foi
   implementada citando explicitamente esta tela). Esta tela só IMPORTA a
   mesma constante (nunca redefine um segundo valor); não há necessidade de
   mover a constante para `components.py`/`thresholds.py` -- mover algo que
   já está correto e já documentado não deixaria o código mais limpo, só
   deslocaria a mesma explicação para outro arquivo.
2. **Escopo por governador.** Igual às Telas 1 e 2 (e à luz do bug real que a
   revisão da Tela 1 pegou, ver issue #111): toda a lógica desta tela --
   tema em maior ascensão, linha do tempo, lista de comentários -- recebe
   `df_sentiment`/`df_sentiment_history` JÁ FILTRADO ao governador
   selecionado no cabeçalho, nunca o histórico combinado dos 27 perfis. Uma
   "crise" de negatividade é sempre uma crise DE UM PERFIL específico para a
   analista de assessoria que está olhando aquele governador -- misturar
   todos os perfis faria o tema em ascensão de um governador com pouco
   volume ser mascarado (ou distorcido) pelo volume de outro.
3. **Janela da linha do tempo e frase de decisão.** Vêm de
   `load_sentiment_history()` (não só a última execução) -- "14 dias" na
   especificação original é linguagem de calendário, mas o pipeline não tem
   agendamento fixo (ver ADR 0021, ponto de atrito 4; mesma ressalva já
   registrada em `dashboard/core/deltas.py`). Agregado por `_run_id`
   (ordenado por `_generated_at` quando disponível), não por um calendário
   fixo de 14 dias corridos.
4. **Lista de comentários.** Vem de `load_sentiment()` (execução mais
   recente), não do histórico -- é literalmente "os comentários negativos
   mais recentes", e `load_sentiment_history()` acumularia execuções antigas
   que não fazem sentido numa lista de "agora" (ver issue #113, Implementation
   Decisions, que também especifica esta fonte para a lista).
5. **Privacidade -- não-negociável.** `_comentarios_negativos_recentes`
   constrói o `DataFrame` de saída por ALLOW-LIST (só `comentario`/`tema`,
   nunca por remover colunas de uma cópia do original) -- estruturalmente
   impossível vazar `ownerUsername` (ou qualquer outra coluna de identidade)
   por esquecimento futuro. Ver teste dedicado em
   `tests/test_dashboard_screens_radar.py`.
6. **Critério de alerta ("warn") por janela de publicação (ADR 0025 / issue
   #153).** `_tema_maior_alta_negatividade` deixou de comparar as 2
   execuções mais recentes (`week_over_week`) e passou a comparar a janela
   atual de `deltas.JANELA_ALERTA_NEGATIVIDADE_DIAS` dias por data de
   PUBLICAÇÃO contra a janela imediatamente anterior
   (`deltas.compare_publication_window`) -- a decisão 3 acima (linha do
   tempo agregada por `_run_id`) continua valendo só para o GRÁFICO; o
   critério que alimenta a frase de decisão/nível do semáforo agora é este.
   O ramo "danger" (limiar absoluto `LIMIAR_NEGATIVIDADE_ALERTA`) não muda.
7. **2ª leitura exploratória: tema mais negativo no período (ADR 0026 /
   issue #154).** `_maior_alta_negatividade` foi portada sem redesenho de
   `resumo.py` (que perdeu o destaque "Tema em alta de negatividade" na
   mesma issue) -- responde "qual tópico concentrou mais negatividade no
   período escolhido pela analista", reaproveitando o MESMO `st.date_input`
   já usado pela linha do tempo (decisão 3), nunca um segundo widget.
   Visual e funcionalmente distinta da frase de decisão no topo (que usa
   `_tema_maior_alta_negatividade`, decisão 6): uma é alerta automático de
   tendência recente, a outra é consulta livre de período.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.core import data
from dashboard.core.components import decision_band, footnote, stage_label
from dashboard.core.deltas import (
    LIMIAR_NEGATIVIDADE_ALERTA,
    aggregate_pct_negative_by_publication_day,
    compare_publication_window,
    deduplicate_by_first_seen,
    filter_by_date_range,
    normalize_date_input_range,
    parse_publication_dates,
    quebrar_em_segmentos,
)
from dashboard.core.theme import COLORS

_PLACEHOLDER_SEM_GOVERNADOR = "—"
_PLACEHOLDER_SEM_TEMA = "—"


# ---------------------------------------------------------------------------
# Normalização / seleção de governador (duplicado de `resumo.py`/`produzir.py`
# -- mesmo raciocínio: cada tela fica autocontida, sem depender de outra tela
# nem de `src/dashboard/filters.py`, que está sendo descontinuado tela por
# tela pela ADR 0021).
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
# Agregação por tema (para a frase de decisão -- tema em maior ascensão)
# ---------------------------------------------------------------------------

_COLUNAS_OBRIGATORIAS_TOPICO = {
    "Topic", "Name", "sentiment_label", "timestamp", "id_comment", "_run_id"
}


def _comentarios_com_topico_deduplicados(df_sentiment_history: pd.DataFrame) -> pd.DataFrame | None:
    """Preparação compartilhada pelas duas leituras de "tema em maior
    negatividade" desta tela (`_tema_maior_alta_negatividade`, o alerta
    principal por janela fixa, e `_maior_alta_negatividade`, a 2ª leitura
    exploratória por período livre -- ADR 0026 / issue #154): valida as
    colunas obrigatórias, descarta comentários sem `Topic` atribuído
    (BERTopic não rodou) e deduplica por `id_comment`/menor `_run_id` (ver
    `deltas.deduplicate_by_first_seen`) -- evita contar duas vezes um
    comentário recoletado em execuções sobrepostas. `None` (nunca exceção)
    se `df_sentiment_history` estiver vazio, faltar coluna obrigatória, ou
    nenhum comentário tiver `Topic`."""
    if df_sentiment_history.empty or not _COLUNAS_OBRIGATORIAS_TOPICO.issubset(
        df_sentiment_history.columns
    ):
        return None
    df = df_sentiment_history.dropna(subset=["Topic"])
    if df.empty:
        return None
    return deduplicate_by_first_seen(df)


def _tema_maior_alta_negatividade(df_sentiment_history: pd.DataFrame) -> dict | None:
    """Tema (`Topic`) com a maior variação POSITIVA de `% negativo` entre a
    janela atual de `deltas.JANELA_ALERTA_NEGATIVIDADE_DIAS` dias (por data
    de PUBLICAÇÃO) e a janela imediatamente anterior, via
    `core.deltas.compare_publication_window` (ADR 0025 / issue #153) --
    substitui a comparação por execução (`week_over_week`) usada antes desta
    ADR (ver issue #113 original), porque o pipeline não tem cadência fixa
    de execução (ADR 0021, ponto de atrito 4).

    `df_sentiment_history` já filtrado ao governador selecionado (ver
    `render()`). Deduplica por `id_comment`/menor `_run_id` antes de agregar
    (ver `deltas.deduplicate_by_first_seen`) -- evita contar duas vezes um
    comentário recoletado em execuções sobrepostas.

    `None` se não houver histórico suficiente na janela atual (menos de 1
    janela completa de dado) ou se nenhum tema tiver alta de negatividade
    (todo `delta_percentual` nulo, zero ou negativo) -- nunca força um "tema
    em alta" artificial quando a negatividade está estável ou caindo em
    todos os temas com dado real."""
    df = _comentarios_com_topico_deduplicados(df_sentiment_history)
    if df is None:
        return None
    df = df.assign(_is_negative=(df["sentiment_label"] == "negative").astype(float))

    resultado = compare_publication_window(df, value_col="_is_negative", key_col="Topic")
    if not resultado:
        return None

    candidatos = {
        topic: (atual, delta, anterior)
        for topic, (atual, delta, anterior) in resultado.items()
        if delta is not None and not pd.isna(delta) and delta > 0
    }
    if not candidatos:
        return None

    topic_id = max(candidatos, key=lambda t: candidatos[t][1])
    pct_atual, delta_percentual, pct_anterior = candidatos[topic_id]

    nome = df.loc[df["Topic"] == topic_id, "Name"].iloc[-1]
    return {
        "topic": topic_id,
        "name": nome,
        "pct_atual": pct_atual,
        "pct_anterior": pct_anterior,
        "delta_percentual": delta_percentual,
    }


# ---------------------------------------------------------------------------
# Tema mais negativo NO PERÍODO -- 2ª leitura exploratória (ADR 0026 / issue
# #154), portada sem redesenho de `resumo.py::_maior_alta_negatividade`
# (mesma lógica/assinatura/testes, só realocada). DIFERENTE de
# `_tema_maior_alta_negatividade` acima: esta função responde "qual tópico
# concentrou mais negatividade no período que a analista escolheu" (consulta
# exploratória, sem noção de "atual vs. anterior"); aquela responde "qual
# tópico subiu mais na janela fixa de `deltas.JANELA_ALERTA_NEGATIVIDADE_DIAS`
# dias" (alerta automático). `render()` chama esta reaproveitando o MESMO
# `st.date_input` já usado pela linha do tempo -- nunca um segundo widget de
# calendário.
# ---------------------------------------------------------------------------


def _maior_alta_negatividade(
    df_sentiment_history: pd.DataFrame,
    data_inicio: object | None = None,
    data_fim: object | None = None,
) -> dict | None:
    """Tópico de comentário (`Topic`/`Name`) com maior `% negativo` agregado
    no intervalo `[data_inicio, data_fim]` de datas de PUBLICAÇÃO (ADR 0023).

    `data_inicio`/`data_fim` `None` (default) usa todo o histórico
    disponível.

    IMPORTANTE: `df_sentiment_history` deve chegar aqui já filtrado ao
    governador selecionado (ver `render()`, `_filtrar_por_governador`) -- esta
    função não faz nenhum filtro por `inputUrl` sozinha. Passar o histórico
    de todos os 27 perfis produz o tópico com mais negatividade entre todos
    os governadores combinados, não o do perfil que a analista está olhando.

    Deduplica por `id_comment`/menor `_run_id` antes de agregar (ver
    `deltas.deduplicate_by_first_seen`) -- evita contar duas vezes um
    comentário recoletado em execuções sobrepostas.

    `None` se não houver dado suficiente (nenhum tópico atribuído -- BERTopic
    não rodou --, nenhum comentário no intervalo filtrado, ou nenhum tópico
    com negatividade > 0) -- não força um "destaque" artificial quando o
    período foi estável ou positivo em todos os tópicos."""
    df = _comentarios_com_topico_deduplicados(df_sentiment_history)
    if df is None:
        return None
    df = df.assign(_data_publicacao=parse_publication_dates(df)).dropna(subset=["_data_publicacao"])
    df = filter_by_date_range(df, "_data_publicacao", data_inicio, data_fim)
    if df.empty:
        return None

    agregado = (
        df.groupby(["Topic", "Name"])["sentiment_label"]
        .apply(lambda s: (s == "negative").mean())
        .rename("pct_negativo")
        .reset_index()
    )
    candidatos = agregado[agregado["pct_negativo"] > 0]
    if candidatos.empty:
        return None

    linha = candidatos.sort_values("pct_negativo", ascending=False).iloc[0]
    return {
        "topic": linha["Topic"],
        "name": linha["Name"],
        "pct_negativo": linha["pct_negativo"] * 100,
    }


# ---------------------------------------------------------------------------
# Nível do semáforo / frase de decisão (issue #113, user stories 1-2, 6-7)
# ---------------------------------------------------------------------------


def _nivel_semaforo(
    pct_negativo_atual: float | None,
    delta_percentual: float | None,
    limiar: float = LIMIAR_NEGATIVIDADE_ALERTA,
) -> str:
    """Nível da faixa de decisão -- `"danger"`/`"warn"`/`"good"` (nunca
    `"info"` nesta tela: mesmo sem dado suficiente, o estado correto é
    "sem alertas hoje" em verde, não uma cor neutra -- ver issue #113, user
    story 7).

    - `"danger"`: `pct_negativo_atual` cruzou (>=) `limiar`.
    - `"warn"`: não cruzou, mas subiu vs. a execução anterior
      (`delta_percentual > 0`).
    - `"good"`: estável ou caindo (`delta_percentual <= 0` ou ausente), OU
      não há `pct_negativo_atual` calculável -- inclui o caso "sem
      comentários negativos suficientes para preocupar" (issue #113, user
      story 7): nunca um gráfico/estado vazio confuso, sempre "sem alertas
      hoje" em verde."""
    if pct_negativo_atual is None or pd.isna(pct_negativo_atual):
        return "good"
    if pct_negativo_atual >= limiar:
        return "danger"
    if delta_percentual is not None and not pd.isna(delta_percentual) and delta_percentual > 0:
        return "warn"
    return "good"


def _frase_decisao(nivel: str, tema: dict | None) -> str:
    """Texto da faixa de decisão -- sempre a primeira coisa lida na tela
    (ver CONTEXT.md, "Frase de decisão"). Porcentagens sempre arredondadas
    para inteiro (issue #113, user story 8)."""
    if tema is None:
        return (
            "Sem alertas hoje -- nenhum tema com alta de negatividade nas "
            "execuções disponíveis (ou dado insuficiente para comparar)."
        )

    nome = tema["name"] if pd.notna(tema.get("name")) else f"tópico {tema['topic']}"
    pct_atual = round(tema["pct_atual"] * 100)
    pct_anterior = tema.get("pct_anterior")
    if pct_anterior is not None and not pd.isna(pct_anterior):
        variacao = f"subiu de {round(pct_anterior * 100)}% para {pct_atual}%"
    else:
        variacao = f"está em {pct_atual}%"

    if nivel == "danger":
        return (
            f'Atenção: negatividade em "{nome}" {variacao} -- cruzou o '
            f"limite de alerta ({round(LIMIAR_NEGATIVIDADE_ALERTA * 100)}%)."
        )
    if nivel == "warn":
        return (
            f'Fique de olho: negatividade em "{nome}" {variacao}, mas '
            "ainda não cruzou o limite de alerta."
        )
    return "Sem alertas hoje -- negatividade estável ou em queda nos temas com dado real."


# ---------------------------------------------------------------------------
# Linha do tempo (% negativo agregado por DIA DE PUBLICAÇÃO -- ADR 0023,
# substitui a agregação por execução da issue #113 original: comentários e
# discurso têm data real de publicação, independente de quando a coleta
# rodou -- ver módulo docstring de `dashboard/core/deltas.py`). A agregação
# em si (dedup + groupby por dia) vem de
# `deltas.aggregate_pct_negative_by_publication_day`; as duas funções abaixo
# só recortam essa série pro que a tela precisa: o intervalo escolhido pela
# analista, e a quebra em segmentos pra não desenhar uma linha contínua
# entre dois dias distantes sem dado real entre eles.
# ---------------------------------------------------------------------------


def _filtrar_por_intervalo(
    df_timeline: pd.DataFrame,
    data_inicio: object | None,
    data_fim: object | None,
) -> pd.DataFrame:
    """Restringe `df_timeline` (colunas `data`/`pct_negativo`, já agregado por
    dia de publicação) ao intervalo `[data_inicio, data_fim]`, inclusive --
    fina camada sobre `deltas.filter_by_date_range` (compartilhada com o
    destaque de sentimento do Resumo, ADR 0023) fixando a coluna de data
    desta tela."""
    return filter_by_date_range(df_timeline, "data", data_inicio, data_fim)


def _cores_marcador(valores_pct: pd.Series, limiar_pct: float) -> list[str]:
    """Cor de cada marcador da linha do tempo (ADR 0023): vermelho
    (`COLORS["danger"]["fg"]`) se o ponto cruzou `limiar_pct`, cor neutra
    (`COLORS["muted"]`) caso contrário -- nunca a linha em si, que
    permanece sempre neutra (ver docstring de `render()`: colorir o
    segmento inteiro entre dois pontos distantes sugeriria uma tendência
    que o dado real não sustenta)."""
    return [COLORS["danger"]["fg"] if v >= limiar_pct else COLORS["muted"] for v in valores_pct]


# Quebra de linha em gap > `deltas.GAP_DIAS_QUEBRA_LINHA` dias: usa
# `deltas.quebrar_em_segmentos` (extraída daqui pela ADR 0024, quando ganhou
# um segundo consumidor real em `produzir.py`).


# ---------------------------------------------------------------------------
# Lista de comentários negativos mais recentes (issue #113, user stories 4-5)
# ---------------------------------------------------------------------------


def _comentarios_negativos_recentes(
    df_sentiment: pd.DataFrame,
    df_topic_priority: pd.DataFrame,
    topico_alvo: object | None,
    n: int = 10,
) -> pd.DataFrame:
    """Lista dos `n` comentários negativos mais recentes (mais recente
    primeiro, via `_generated_at`/`_run_id`) do `topico_alvo` (tema em maior
    ascensão -- ver `_tema_maior_alta_negatividade`); se `topico_alvo` for
    `None` (nenhum tema em alta identificável), lista os comentários
    negativos mais recentes em geral, sem filtro de tema.

    REQUISITO DE PRIVACIDADE NÃO-NEGOCIÁVEL (issue #113, user story 5): o
    resultado é construído por ALLOW-LIST -- só as colunas `comentario`
    (texto) e `tema` (selo) são incluídas na saída, nunca por remoção de
    colunas de uma cópia do `DataFrame` de origem. Isso torna
    estruturalmente impossível vazar `ownerUsername` (ou qualquer outra
    coluna de identidade presente em `governor_sentiment`) por esquecimento
    futuro, mesmo que novas colunas de autor sejam adicionadas ao schema.
    Ver teste dedicado (`test_comentarios_negativos_recentes_nunca_expoe_autor`)
    em `tests/test_dashboard_screens_radar.py`.

    Selo de tema: usa `Name` já presente em `df_sentiment` quando
    disponível; senão cruza `Topic` com `df_topic_priority`
    (`load_topic_priority()`) para o nome do tópico do BERTopic de
    comentário. `_PLACEHOLDER_SEM_TEMA` quando nenhuma das duas fontes tiver
    o nome. `DataFrame` vazio (colunas `comentario`/`tema`, nunca exceção)
    se não houver comentário negativo (do tema, se filtrado)."""
    colunas_saida = ["comentario", "tema"]
    required = {"text", "sentiment_label", "_run_id"}
    if df_sentiment.empty or not required.issubset(df_sentiment.columns):
        return pd.DataFrame(columns=colunas_saida)

    df = df_sentiment[df_sentiment["sentiment_label"] == "negative"].copy()
    if topico_alvo is not None and "Topic" in df.columns:
        df = df[df["Topic"] == topico_alvo]
    if df.empty:
        return pd.DataFrame(columns=colunas_saida)

    ordenar_por = "_generated_at" if "_generated_at" in df.columns else "_run_id"
    df = df.sort_values(ordenar_por, ascending=False)

    if "Name" in df.columns and df["Name"].notna().any():
        temas = df["Name"]
    elif (
        not df_topic_priority.empty
        and "Topic" in df.columns
        and {"Topic", "Name"}.issubset(df_topic_priority.columns)
    ):
        mapa_nomes = df_topic_priority.drop_duplicates(subset=["Topic"]).set_index("Topic")["Name"]
        temas = df["Topic"].map(mapa_nomes)
    else:
        temas = pd.Series([None] * len(df), index=df.index)

    resultado = pd.DataFrame(
        {"comentario": df["text"].to_numpy(), "tema": temas.to_numpy()}
    )
    return resultado.head(n).reset_index(drop=True)


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
        stage_label("Convert (Contribuir)")
        st.info(
            "Nenhum governador disponível ainda -- rode a pipeline "
            "(`uv run python pipeline.py`) para popular o dashboard."
        )
        footnote()
        return

    nome_selecionado = st.selectbox("Governador", options=list(options.keys()))
    governor_url = options[nome_selecionado]
    stage_label("Convert (Contribuir)")

    # ---- Dado bruto ----
    # Frase de decisão + linha do tempo: histórico completo (não só a última
    # execução), já filtrado a ESTE governador -- ver docstring do módulo,
    # decisões 2 e 3.
    df_sentiment_history_governador = _filtrar_por_governador(
        data.comments_only(data.load_sentiment_history()), governor_url
    )
    # Lista de comentários: execução mais recente, também já filtrada ao
    # governador -- ver docstring do módulo, decisão 4.
    df_sentiment_governador = _filtrar_por_governador(
        data.comments_only(data.load_sentiment()), governor_url
    )
    df_topic_priority = data.load_topic_priority()

    tema_em_alta = _tema_maior_alta_negatividade(df_sentiment_history_governador)

    pct_negativo_atual = tema_em_alta["pct_atual"] if tema_em_alta else None
    delta_percentual = tema_em_alta["delta_percentual"] if tema_em_alta else None
    nivel = _nivel_semaforo(pct_negativo_atual, delta_percentual)

    # ---- Frase de decisão ----
    decision_band(_frase_decisao(nivel, tema_em_alta), level=nivel)

    # ---- Linha do tempo ----
    # ADR 0023: eixo por data real de publicação do comentário, não por
    # execução -- o filtro de calendário abaixo afeta SÓ este gráfico, nunca
    # a frase de decisão ou a lista de comentários (ver docstring do módulo).
    st.markdown("#### % de comentários negativos por data de publicação")
    df_timeline_completo = aggregate_pct_negative_by_publication_day(
        df_sentiment_history_governador
    )
    # ADR 0026 / issue #154: `data_inicio`/`data_fim` inicializados aqui
    # (fora do `if`/`else` abaixo) porque a 2ª leitura exploratória logo
    # depois da linha do tempo reaproveita o MESMO `st.date_input` -- nunca
    # um segundo widget de calendário.
    data_inicio = data_fim = None
    if df_timeline_completo.empty:
        st.caption("Sem histórico suficiente para mostrar uma linha do tempo ainda.")
    else:
        data_min = df_timeline_completo["data"].min()
        data_max = df_timeline_completo["data"].max()
        intervalo = st.date_input(
            "Período (data de publicação)",
            value=(data_min, data_max),
            min_value=data_min,
            max_value=data_max,
        )
        data_inicio, data_fim = normalize_date_input_range(intervalo)
        df_timeline = _filtrar_por_intervalo(df_timeline_completo, data_inicio, data_fim)

        if df_timeline.empty:
            st.caption("Nenhum comentário publicado no período selecionado.")
        else:
            limiar_pct = LIMIAR_NEGATIVIDADE_ALERTA * 100
            fig = go.Figure()
            for segmento in quebrar_em_segmentos(df_timeline):
                valores_pct = (segmento["pct_negativo"] * 100).round(1)
                cores_marcador = _cores_marcador(valores_pct, limiar_pct)
                fig.add_trace(
                    go.Scatter(
                        x=segmento["data"],
                        y=valores_pct,
                        mode="lines+markers",
                        line={"color": COLORS["muted"]},
                        marker={"color": cores_marcador, "size": 8},
                        showlegend=False,
                    )
                )
            fig.add_hline(
                y=limiar_pct,
                line_dash="dash",
                line_color=COLORS["danger"]["fg"],
                annotation_text=f"Limite de alerta ({round(limiar_pct)}%)",
                annotation_position="top left",
            )
            fig.update_layout(
                yaxis_title="% negativo",
                xaxis_title="Data de publicação",
                showlegend=False,
                margin={"t": 30, "b": 10},
            )
            st.plotly_chart(fig, use_container_width=True)

    # ---- Tema mais negativo no período (2ª leitura -- ADR 0026 / issue #154) ----
    # Consulta exploratória, visual e funcionalmente distinta da frase de
    # decisão no topo (alerta automático de tendência recente): reaproveita
    # o MESMO `data_inicio`/`data_fim` do filtro de calendário acima, nunca
    # um segundo widget. Ver docstring de `_maior_alta_negatividade`.
    st.markdown("#### Tema mais negativo no período")
    st.caption(
        "Leitura exploratória do período selecionado acima -- não é um "
        "alerta automático, é uma consulta livre (diferente da frase de "
        "decisão no topo da tela)."
    )
    tema_periodo = _maior_alta_negatividade(df_sentiment_history_governador, data_inicio, data_fim)
    if tema_periodo is None:
        st.caption("Nenhum tema com negatividade no período selecionado.")
    else:
        st.write(
            f"**{tema_periodo['name']}** -- "
            f"{tema_periodo['pct_negativo']:.1f}% de negatividade no período."
        )

    # ---- Lista de comentários negativos mais recentes ----
    st.markdown("#### Comentários negativos mais recentes")
    if tema_em_alta is not None:
        st.caption(f"Tema em maior ascensão de negatividade: {tema_em_alta['name']}")
    topico_alvo = tema_em_alta["topic"] if tema_em_alta is not None else None
    df_comentarios = _comentarios_negativos_recentes(
        df_sentiment_governador, df_topic_priority, topico_alvo
    )
    if df_comentarios.empty:
        st.caption("Nenhum comentário negativo recente para este governador.")
    else:
        df_exibir = df_comentarios.rename(columns={"comentario": "Comentário", "tema": "Tema"})
        df_exibir["Tema"] = df_exibir["Tema"].fillna(_PLACEHOLDER_SEM_TEMA)
        st.dataframe(df_exibir, hide_index=True, width="stretch")

    footnote()
