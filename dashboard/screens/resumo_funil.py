"""Sub-aba "Funil de engajamento" do Resumo (ADR 0031 / issue #183; nasceu
como a Tela 6 da ADR 0021 / issue #114). Segue o seletor único do Resumo
(`resumo.py`); em "Todos os Governadores" cada estágio é a MÉDIA por
governador (cada perfil pesa igual, ADR 0027), nunca a soma.

Responde à tese central do TCC (Cap. 6): o funil COBRA-RACE completo, dos 4
estágios (Reach·Alcançar -> Act·Consumir -> Convert·Contribuir ->
Engage·Criar), como um funil de largura em escala logarítmica (3 etapas) +
bloco do Engage + taxas de passagem entre as etapas + gargalo + ação
recomendada. Substituiu `pages/05_funil.py` (ADR 0020) -- ver ADR 0021,
"Opção C híbrida": esta tela é a "espinha conceitual" da ferramenta, e cada
uma das outras 5 telas carrega só um `stage_label()` discreto apontando para
o estágio correspondente.

Mesma estrutura de módulo das demais telas: funções puras nomeadas, testadas em
`tests/test_dashboard_screens_resumo_funil.py`; `render()` só orquestra I/O do
Streamlit sobre o resultado dessas funções.

Decisões de implementação registradas aqui (ver PR da issue #114 para o
texto completo):

1. **Ambiguidade de spec resolvida -- fonte de `videoPlayCount`.** A issue
   pede "soma de `videoPlayCount` de `load_clusters_content()` filtrado a
   `content_type=='reel'`", mas `GOLD_CLUSTERS_SCHEMA` (a tabela por trás de
   `load_clusters_content()`) NÃO tem `videoPlayCount` nem `inputUrl` -- só
   `id_reel`/`ownerUsername`/`cluster_*`/`content_type` (conferido contra
   `src/schemas_delta.py` e contra a docstring já existente de
   `dashboard/core/data.py::load_reels_content`, que documenta exatamente
   esta mesma lacuna para outro propósito). `videoPlayCount` real mora em
   `reels_clean` (Silver, `load_reels_content()`, `SILVER_REELS_SCHEMA`).
   Resolução: mesmo join `id`/`id_reel` já estabelecido em
   `produzir.py::_clusters_reel_do_governador`/`resumo.py::_melhor_post` --
   `load_clusters_content()` filtrado a `content_type=='reel'` decide QUAIS
   reels entram na conta (`governor_clusters` também grava clusterização de
   posts do feed sob o mesmo nome de coluna `id_reel`, ver ADR 0020 Ficha 2
   / issue #87 -- o filtro de `content_type` é o que impede um post de feed
   de entrar na soma de "Reach"), `reels_clean` fornece o valor real de
   `videoPlayCount` e o `inputUrl` para o filtro de governador.
2. **Null handling de `videoPlayCount` -- decisão explícita (issue #114,
   Implementation Decisions e user story 7).** Reels sem `videoPlayCount`
   gravado (coluna nullable -- a Apify nem sempre retorna esse campo) são
   EXCLUÍDOS da soma (`.dropna()` antes de somar), NUNCA tratados como zero.
   Tratar como zero afirmaria "o Instagram reportou zero visualizações"
   quando na verdade o dado simplesmente não foi coletado -- uma alegação
   mais forte e potencialmente enganosa do que omitir o reel da soma.
   Excluir ainda pode SUBESTIMAR o total real, mas nunca finge uma precisão
   que não existe. Em qualquer caso (todos os reels nulos, nenhum reel, ou
   tabela vazia), o retorno de `_visualizacoes_reels_governador` é sempre
   `0.0`, nunca `NaN` -- ver teste dedicado
   (`test_visualizacoes_reels_governador_nunca_retorna_nan`).
3. **Rótulo "Visualizações", nunca "Alcance".** A palavra "Alcance" é
   reservada, em todo o resto da ferramenta, à métrica ilustrativa de
   alcance-proxy (engajamento) usada por NSM/Score ICE (ver CONTEXT.md,
   "Alcance" vs. "Visualizações") -- confundir os dois números misrepresenta
   a própria distinção que o TCC faz entre dado real e proxy. Nenhuma string
   renderizada por este módulo usa a palavra "Alcance" para o estágio Reach.
4. **Engage·Criar -- volume de UGC orgânico (ADR 0032, que revisa a decisão
   original da issue #114).** A decisão original proibia qualquer leitura de
   tabela `ugc_*` (a barra de Engage era um texto fixo "em construção").
   `governor_ugc_mentions` passou a existir (piloto de 2026-09-19), então o
   Engage agora mostra o NÚMERO DE POSTS de UGC ORGÂNICO do governador (o
   "volume de UGC" do nível Criar do COBRA; publi paga fica de fora, ver
   `_engage_por_governador`). A taxa Convert -> Engage (posts de UGC por
   comentário positivo) aparece num selo entre o funil e o bloco do Engage
   (`_taxa_engage`), mas NUNCA entra em `_taxas_passagem` nem na identificação
   do gargalo: as unidades e as populações são diferentes (posts de terceiros
   x comentários). Os dados atuais são só uma AMOSTRA DE TESTE (no máximo 5
   posts por governador): enquanto o máximo por governador for <= 5
   (`_ugc_e_amostra_piloto`), o comparativo ▲/▼ do Engage fica oculto (seria
   ruído); com uma coleta completa ele aparece sozinho. A tela não exibe
   aviso de "piloto". O Engage fica num bloco SEPARADO abaixo do funil (não é
   uma 4ª etapa do desenho), porque o volume de UGC pode ser maior que o de
   Convert e quebraria o afunilamento. `load_discourse_topics()` continua NÃO
   sendo usado como proxy numérico.
5. **Taxas de passagem -- dado insuficiente é `None`, nunca zero.**
   `_taxas_passagem` só calcula uma taxa quando o estágio de origem tem
   valor real (> 0); do contrário retorna `None` para aquela taxa --
   `_identificar_gargalo` exclui candidatos `None` do cálculo, nunca os
   trata como "taxa de 0%" (que seria uma afirmação diferente e mais forte
   do que "não sei"). `Convert/Engage` é exibida num selo próprio, mas nunca entra aqui nem no
   gargalo (ver decisão 4).
6. **Gargalo -- desempate determinístico.** Em caso de empate entre `"act"`
   e `"convert"`, o desempate favorece o estágio mais cedo no funil
   (`_ORDEM_ESTAGIOS_GARGALO` = Act antes de Convert) -- um gargalo mais
   cedo composta sobre todo o resto da jornada, então é o mais acionável de
   resolver primeiro. Testado explicitamente
   (`test_identificar_gargalo_empate_prefere_estagio_mais_cedo`).
7. **Escalonamento da faixa de decisão -- independente do gargalo.** Se
   `Convert` (comentários positivos) está caindo vs. a execução anterior
   (`core.deltas.week_over_week` sobre a contagem bruta, não a taxa), a
   faixa de decisão sobe para amarelo mesmo que `"convert"` não seja o
   estágio de menor taxa absoluta -- ver `_nivel_decisao`. Esta escalada é
   deliberadamente independente da identificação do gargalo (que continua
   sendo só "menor taxa entre os pares com dado real"): a cor da faixa
   comunica urgência, o selo "gargalo" na barra comunica onde agir -- os
   dois sinais podem discordar (ex.: gargalo insuficiente para calcular,
   mas Convert ainda assim caindo).
8. **Ação recomendada -- negatividade em alta tem prioridade sobre o
   gargalo do funil.** Mesmo critério de prioridade já usado em
   `resumo.py::_nivel_semaforo` (que também checa negatividade antes de
   qualquer outro sinal): uma crise de negatividade é o sinal mais urgente,
   então `_acao_recomendada` aponta para "Ver Radar de crise" antes de
   considerar o gargalo do funil, mesmo quando os dois sinais estão
   presentes ao mesmo tempo.
9. **Navegação -- `st.session_state` via `on_click`, não `st.page_link`.**
   `dashboard/app.py` (issue #110) usa `st.radio` (não multipágina nativa do
   Streamlit) para navegação. O botão de ação desta sub-aba grava o rótulo da
   Tela-alvo (Radar de crise / O que produzir) em
   `st.session_state["tela_selecionada"]` (a mesma `key` do `st.radio` de
   `app.py`) através do callback `_navegar_para`
   passado a `on_click` -- NUNCA inline no corpo do script: `app.py` já
   instanciou o `st.radio` antes de chamar `render()`, então escrever nessa
   `key` fora de um callback levanta `StreamlitAPIException` (bug real
   encontrado só ao rodar o app de verdade, já que o repo testa por
   inspeção de fonte -- ver decisão de não usar `st.testing.AppTest` em
   `tests/test_dashboard_screens_resumo.py`). O próprio `st.button(...,
   on_click=...)` já dispara o rerun -- não chamamos `st.rerun()` de novo.
   No próximo render, o `st.radio` lê o valor já setado em `session_state`
   como seleção inicial. Documentado também no PR desta issue.
10. **Funil em escala logarítmica + comparativo (ADR 0032).** As etapas
    têm unidades e ordens de grandeza muito diferentes (ex.: ~1,4 milhão de
    visualizações -> ~118 mil curtidas -> 42 comentários positivos), então a
    largura de cada trapézio é proporcional ao log10 do valor (com largura
    mínima), e a tela avisa isso. As taxas de passagem ficam em selos ENTRE as
    etapas ("N% avançam"), e, com um governador selecionado, cada etapa mostra
    ▲/▼ + a diferença relativa do VALOR ABSOLUTO contra a MEDIANA dos demais
    governadores (só quem tem valor > 0 na etapa). Em "Todos" não há
    comparativo (não há "demais"). Valor absoluto reflete o tamanho da
    audiência: a seta mostra escala, e o selo de taxa mostra eficiência.
11. **Texto sempre associativo, nunca causal.** Toda frase de decisão/ação
    usa "associado a"/"está relacionado a" -- nunca "causa"/"gera" no
    sentido causal (issue #114, user story 8, hard requirement de
    honestidade analítica para o TCC).
"""

from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from dashboard.core import data
from dashboard.core.components import footnote
from dashboard.core.deltas import LIMIAR_NEGATIVIDADE_ALERTA, week_over_week
from dashboard.core.theme import COLORS
from dashboard.screens.resumo_comum import (
    TODOS_OS_GOVERNADORES,
    _filtrar_por_governador,
    _normalize_url,
)

_PLACEHOLDER_SEM_DADO = "—"

# Rótulos de estágio (nomes de negócio, nunca a palavra "Alcance" -- ver
# docstring do módulo, decisão 3).
_ESTAGIO_REACH = "reach"
_ESTAGIO_ACT = "act"
_ESTAGIO_CONVERT = "convert"
_ESTAGIO_ENGAGE = "engage"

# Ordem de desempate de gargalo -- ver docstring do módulo, decisão 6.
_ORDEM_ESTAGIOS_GARGALO = [_ESTAGIO_ACT, _ESTAGIO_CONVERT]

# Chave fixa para `week_over_week` sobre séries já filtradas a 1 governador
# (a função sempre espera uma coluna-chave para pivotar, mesmo quando só há
# 1 governador de interesse -- mesmo raciocínio de `radar.py` para tópicos).
_CHAVE_GOVERNADOR_UNICO = "governador_selecionado"

_LABEL_TELA_PRODUZIR = "O que produzir"
_LABEL_TELA_RADAR = "Radar de crise"
_ACAO_PRODUZIR = "produzir"
_ACAO_RADAR = "radar"

_NOTA_FUNIL = (
    'Funil COBRA-RACE · "Criar" = volume de UGC orgânico (menções de terceiros) · '
    "Reach baseado em Reels."
)

# Teto de posts de UGC por governador na coleta do piloto (ADR 0020, Ficha 8):
# só alimenta a nota exibida junto do Engage, nunca entra em conta nenhuma.
_MAX_POSTS_UGC_PILOTO = 5


# ---------------------------------------------------------------------------
# Formatação (arredondamento no ponto de exibição)
# ---------------------------------------------------------------------------


def _fmt_int_br(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return _PLACEHOLDER_SEM_DADO
    return f"{round(valor):,}".replace(",", ".")


def _fmt_pct(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return _PLACEHOLDER_SEM_DADO
    return f"{valor * 100:.1f}%"


# ---------------------------------------------------------------------------
# Agregação por estágio (Reach / Act / Convert) -- ver docstring do módulo,
# decisões 1-3.
# ---------------------------------------------------------------------------


def _visualizacoes_reels_governador(
    df_clusters: pd.DataFrame, df_reels: pd.DataFrame, governor_url: str
) -> float:
    """Reach·Alcançar: soma de `videoPlayCount` (visualizações reais) dos
    Reels do governador selecionado -- ver docstring do módulo, decisões 1-2
    para a fonte do dado e o tratamento de nulo. Retorna sempre `float`,
    nunca `NaN`/exceção: `0.0` quando qualquer tabela estiver vazia, sem
    match de governador, sem reel com cluster `content_type == 'reel'`, ou
    quando todo `videoPlayCount` do resultado for nulo."""
    if df_clusters.empty or df_reels.empty or not governor_url:
        return 0.0
    if (
        "content_type" not in df_clusters.columns
        or "id_reel" not in df_clusters.columns
    ):
        return 0.0

    clusters_reel = df_clusters[df_clusters["content_type"] == "reel"]
    if clusters_reel.empty:
        return 0.0

    reels_governador = _filtrar_por_governador(df_reels, governor_url)
    if reels_governador.empty or "id" not in reels_governador.columns:
        return 0.0
    if "videoPlayCount" not in reels_governador.columns:
        return 0.0

    merged = reels_governador.merge(
        clusters_reel, left_on="id", right_on="id_reel", how="inner"
    )
    if merged.empty:
        return 0.0

    # Decisão de null handling (ver docstring do módulo, decisão 2): exclui
    # da soma reels sem `videoPlayCount` gravado, nunca conta como zero. Uma
    # soma sobre uma Series totalmente nula/vazia já retorna 0.0 (não NaN),
    # mas o `.dropna()` explícito documenta a decisão em vez de depender do
    # comportamento default do pandas.
    return float(merged["videoPlayCount"].dropna().sum())


def _consumir_likes_governador(df_engagement: pd.DataFrame, governor_url: str) -> float:
    """Act·Consumir: `likesSum` de `governor_engagement` (já pré-agregado por
    perfil pelo pipeline -- não é uma soma calculada aqui) para o governador
    selecionado. `0.0` (nunca `NaN`/exceção) se a tabela estiver vazia, sem
    match, ou sem a coluna."""
    df = _filtrar_por_governador(df_engagement, governor_url)
    if df.empty or "likesSum" not in df.columns:
        return 0.0
    valor = df["likesSum"].iloc[0]
    return 0.0 if pd.isna(valor) else float(valor)


def _contribuir_comentarios_positivos_governador(
    df_sentiment_comments: pd.DataFrame, governor_url: str
) -> float:
    """Convert·Contribuir: contagem de comentários com `sentiment_label ==
    'positive'` (espera `df_sentiment_comments` já filtrado a
    `comments_only()` pelo chamador -- ver `render()`) para o governador
    selecionado. `0.0` (nunca `NaN`/exceção) se vazio, sem match, ou sem a
    coluna."""
    df = _filtrar_por_governador(df_sentiment_comments, governor_url)
    if df.empty or "sentiment_label" not in df.columns:
        return 0.0
    return float((df["sentiment_label"] == "positive").sum())


def _estagios_por_governador(
    df_clusters: pd.DataFrame,
    df_reels: pd.DataFrame,
    df_engagement: pd.DataFrame,
    df_sentiment_comments: pd.DataFrame,
) -> pd.DataFrame:
    """Uma linha por governador de `df_engagement` com `reach`/`act`/
    `convert` (mesmas funções do governador único). `DataFrame` vazio
    (colunas `url`/`reach`/`act`/`convert`) se não houver governador."""
    colunas = ["url", "reach", "act", "convert"]
    if df_engagement.empty or "inputUrl" not in df_engagement.columns:
        return pd.DataFrame(columns=colunas)
    linhas = [
        {
            "url": url,
            "reach": _visualizacoes_reels_governador(df_clusters, df_reels, url),
            "act": _consumir_likes_governador(df_engagement, url),
            "convert": _contribuir_comentarios_positivos_governador(
                df_sentiment_comments, url
            ),
        }
        for url in df_engagement["inputUrl"].dropna().unique()
    ]
    return pd.DataFrame(linhas, columns=colunas)


def _estagios_media(df_por_governador: pd.DataFrame) -> tuple[float, float, float]:
    """`(reach, act, convert)` de "Todos os Governadores": MÉDIA entre
    governadores (cada perfil pesa igual, ADR 0027 -- nunca a soma). Em cada
    estágio só entram governadores com dado real (> 0): zero aqui significa
    "sem dado" (ver `_visualizacoes_reels_governador`), e contá-lo puxaria a
    média para baixo. `0.0` se nenhum governador tiver dado no estágio."""
    valores = []
    for coluna in ("reach", "act", "convert"):
        if df_por_governador.empty:
            valores.append(0.0)
            continue
        serie = df_por_governador[coluna]
        serie = serie[serie > 0]
        valores.append(float(serie.mean()) if not serie.empty else 0.0)
    return (valores[0], valores[1], valores[2])


def _estagios_para_selecao(
    governor_url: str,
    df_clusters: pd.DataFrame,
    df_reels: pd.DataFrame,
    df_engagement: pd.DataFrame,
    df_sentiment_comments: pd.DataFrame,
) -> tuple[float, float, float]:
    """`(reach, act, convert)` para a seleção do seletor único do Resumo:
    governador único, ou média por governador em `TODOS_OS_GOVERNADORES`."""
    if governor_url == TODOS_OS_GOVERNADORES:
        return _estagios_media(
            _estagios_por_governador(
                df_clusters, df_reels, df_engagement, df_sentiment_comments
            )
        )
    return (
        _visualizacoes_reels_governador(df_clusters, df_reels, governor_url),
        _consumir_likes_governador(df_engagement, governor_url),
        _contribuir_comentarios_positivos_governador(
            df_sentiment_comments, governor_url
        ),
    )


# ---------------------------------------------------------------------------
# Engage·Criar -- volume de UGC orgânico (ADR 0032) e comparativo
# ---------------------------------------------------------------------------


def _username_de_url(url) -> str:
    """`https://www.instagram.com/Fulano/?hl=en` -> `fulano` (minúsculo, sem
    query nem barra final). Vazio para nulo."""
    if url is None or (isinstance(url, float) and pd.isna(url)):
        return ""
    return str(url).strip().lower().split("?")[0].rstrip("/").rsplit("/", 1)[-1]


def _engage_por_governador(df_ugc: pd.DataFrame) -> pd.DataFrame:
    """`username`/`engage` por governador: `engage` = NÚMERO de posts de UGC
    ORGÂNICOS (volume de UGC; publi paga é filtrada antes de contar). Linhas
    sem `governor_username` são ignoradas. Vazio (colunas fixas) se a tabela
    estiver vazia ou sem as colunas esperadas."""
    colunas = ["username", "engage"]
    if df_ugc.empty or "governor_username" not in df_ugc.columns:
        return pd.DataFrame(columns=colunas)
    df = df_ugc.dropna(subset=["governor_username"])
    if "is_organic" in df.columns:
        df = df[df["is_organic"].fillna(False).astype(bool)]
    if df.empty:
        return pd.DataFrame(columns=colunas)
    out = df.groupby(df["governor_username"].astype(str).str.lower()).size()
    out = out.astype(float).reset_index()
    out.columns = colunas
    return out


def _ugc_e_amostra_piloto(df_ugc: pd.DataFrame) -> bool:
    """`True` enquanto o máximo de posts de UGC por governador for <= ao teto
    da coleta do piloto (`_MAX_POSTS_UGC_PILOTO`): a contagem reflete o teto,
    não o volume real. Some sozinho quando houver uma coleta completa."""
    por_gov = _engage_por_governador(df_ugc)
    return bool(not por_gov.empty and por_gov["engage"].max() <= _MAX_POSTS_UGC_PILOTO)


def _engage_para_selecao(governor_url: str, df_ugc: pd.DataFrame) -> float:
    """Nº de posts de UGC para a seleção do seletor único. Governador único:
    a contagem dele (`0.0` sem UGC). Todos: MÉDIA por governador, só entre
    quem tem UGC (mesma regra de "média por governador" dos demais estágios)."""
    por_gov = _engage_por_governador(df_ugc)
    if por_gov.empty:
        return 0.0
    if governor_url == TODOS_OS_GOVERNADORES:
        return float(por_gov["engage"].mean())
    linha = por_gov[por_gov["username"] == _username_de_url(governor_url)]
    return float(linha["engage"].iloc[0]) if not linha.empty else 0.0


def _taxa_engage(convert: float, engage: float) -> float | None:
    """Convert -> Engage: posts de UGC por comentário positivo. `None` sem
    dado nos dois lados. Pode passar de 1 (mais posts que comentários). NUNCA
    entra em `_taxas_passagem`/gargalo (ver docstring, decisão 4)."""
    if convert <= 0 or engage <= 0:
        return None
    return engage / convert


def _estagios_com_engage_por_governador(
    df_clusters: pd.DataFrame,
    df_reels: pd.DataFrame,
    df_engagement: pd.DataFrame,
    df_sentiment_comments: pd.DataFrame,
    df_ugc: pd.DataFrame,
) -> pd.DataFrame:
    """`_estagios_por_governador` + coluna `engage` (0.0 = sem UGC)."""
    base = _estagios_por_governador(
        df_clusters, df_reels, df_engagement, df_sentiment_comments
    ).copy()
    por_gov = _engage_por_governador(df_ugc)
    mapa = dict(zip(por_gov["username"], por_gov["engage"], strict=True))
    base["engage"] = [float(mapa.get(_username_de_url(u), 0.0)) for u in base["url"]]
    return base


def _diferencas_vs_mediana(
    valores: dict[str, float], por_governador: pd.DataFrame, governor_url: str
) -> dict | None:
    """Diferença relativa (`valor / mediana - 1`) do valor ABSOLUTO de cada
    estágio do governador selecionado contra a MEDIANA dos DEMAIS
    governadores (só quem tem valor > 0 no estágio, mesma regra do resto do
    módulo). `{"dif": {estagio: float}, "n": int}` ou `None` em "Todos", sem
    pares ou sem nenhum estágio comparável."""
    if governor_url == TODOS_OS_GOVERNADORES or por_governador.empty:
        return None
    chave = _username_de_url(governor_url)
    outros = por_governador[por_governador["url"].map(_username_de_url) != chave]
    dif: dict[str, float] = {}
    n = 0
    for estagio, valor in valores.items():
        if valor <= 0 or estagio not in outros.columns:
            continue
        pares = outros.loc[outros[estagio] > 0, estagio]
        if pares.empty:
            continue
        dif[estagio] = float(valor) / float(pares.median()) - 1
        n = max(n, len(pares))
    return {"dif": dif, "n": n} if dif else None


# ---------------------------------------------------------------------------
# Taxas de passagem + identificação do gargalo -- ver docstring do módulo,
# decisões 5-6.
# ---------------------------------------------------------------------------


def _taxas_passagem(
    reach: float, act: float, convert: float
) -> dict[str, float | None]:
    """`{"act": Act/Reach, "convert": Convert/Act}` -- `None` (nunca
    `ZeroDivisionError`/`inf`) quando o estágio de ORIGEM da taxa não tem
    dado real (ausente, `NaN` ou <= 0), tratado como "dado insuficiente",
    nunca como uma taxa de 0% inventada. `Convert/Engage` nunca é uma chave
    aqui -- é sempre texto fixo em `render()`, nunca calculado."""
    taxas: dict[str, float | None] = {_ESTAGIO_ACT: None, _ESTAGIO_CONVERT: None}
    if reach is not None and not pd.isna(reach) and reach > 0:
        taxas[_ESTAGIO_ACT] = act / reach
    if act is not None and not pd.isna(act) and act > 0:
        taxas[_ESTAGIO_CONVERT] = convert / act
    return taxas


def _identificar_gargalo(taxas: dict[str, float | None]) -> str | None:
    """Estágio (`"act"`/`"convert"`) com a MENOR taxa de passagem entre os
    que têm dado real (`taxas[estagio] is not None`) -- `None` se nenhum
    estágio tiver dado real (dado insuficiente é excluído do cálculo, não
    zerado). Empate: desempatado por `_ORDEM_ESTAGIOS_GARGALO` (Act antes de
    Convert -- ver docstring do módulo, decisão 6)."""
    candidatos = {k: v for k, v in taxas.items() if v is not None and not pd.isna(v)}
    if not candidatos:
        return None
    menor_valor = min(candidatos.values())
    for estagio in _ORDEM_ESTAGIOS_GARGALO:
        if candidatos.get(estagio) == menor_valor:
            return estagio
    return None  # inalcançável -- todo candidato está em _ORDEM_ESTAGIOS_GARGALO


# ---------------------------------------------------------------------------
# Tendência de Convert (contagem bruta) -- escalonamento da faixa de decisão
# (ver docstring do módulo, decisão 7).
# ---------------------------------------------------------------------------


def _agregar_positivos_por_run(
    df_sentiment_history_governador: pd.DataFrame, todos: bool = False
) -> pd.DataFrame:
    """1 linha por `_run_id`: contagem de comentários `sentiment_label ==
    'positive'` -- pré-agregação para `week_over_week` (espera 1 valor já
    pronto por chave por execução). Recebe o histórico JÁ filtrado a
    `comments_only()` e ao governador selecionado (ver `render()`); `_chave`
    é fixa (`_CHAVE_GOVERNADOR_UNICO`) porque o histórico já é de 1
    governador só. `DataFrame` vazio (colunas `_chave`/`_run_id`/
    `qtd_positivos`, nunca exceção) se faltar coluna obrigatória."""
    colunas = ["_chave", "_run_id", "qtd_positivos"]
    required = {"sentiment_label", "_run_id"}
    if df_sentiment_history_governador.empty or not required.issubset(
        df_sentiment_history_governador.columns
    ):
        return pd.DataFrame(columns=colunas)

    if todos and "_chave" in df_sentiment_history_governador.columns:
        # "Todos os Governadores" (ADR 0027): conta por governador em cada
        # execução e tira a MÉDIA entre governadores -- nunca a soma.
        agregado = (
            df_sentiment_history_governador.groupby(["_run_id", "_chave"])[
                "sentiment_label"
            ]
            .apply(lambda s: (s == "positive").sum())
            .groupby("_run_id")
            .mean()
            .rename("qtd_positivos")
            .reset_index()
        )
    else:
        agregado = (
            df_sentiment_history_governador.groupby("_run_id")["sentiment_label"]
            .apply(lambda s: (s == "positive").sum())
            .rename("qtd_positivos")
            .reset_index()
        )
    agregado["_chave"] = _CHAVE_GOVERNADOR_UNICO
    return agregado[colunas]


def _convert_esta_caindo(df_agregado_positivos: pd.DataFrame) -> bool:
    """`True` se a contagem de comentários positivos (Convert·Contribuir)
    caiu vs. a execução anterior (`week_over_week`) -- ver docstring do
    módulo, decisão 7. `False` (nunca exceção) se não houver histórico
    suficiente (< 2 execuções) ou se a variação for nula/ausente/positiva/
    zero."""
    if df_agregado_positivos.empty:
        return False
    resultado = week_over_week(
        df_agregado_positivos,
        value_col="qtd_positivos",
        key_col="_chave",
        run_col="_run_id",
    )
    if not resultado:
        return False
    _, delta = resultado.get(_CHAVE_GOVERNADOR_UNICO, (None, None))
    return bool(delta is not None and not pd.isna(delta) and delta < 0)


def _nivel_decisao(gargalo: str | None, convert_caindo: bool) -> str:
    """Nível da faixa de decisão -- `"warn"`/`"info"` (nunca `"danger"`
    nesta tela: crise de negatividade já tem tela própria, Radar de crise;
    `"good"` reservado para quando não há gargalo nem queda, o que só
    acontece em conjunto com dado insuficiente aqui, então não é exercitado
    na prática -- mantido só por completude).

    - `"warn"`: `convert_caindo` é `True` (checado primeiro -- ver docstring
      do módulo, decisão 7: escalona mesmo que Convert não seja o gargalo de
      menor taxa absoluta) OU há um gargalo identificável.
    - `"info"`: dado insuficiente para qualquer diagnóstico."""
    if convert_caindo:
        return "warn"
    if gargalo is not None:
        return "warn"
    return "info"


_NOMES_GARGALO = {
    _ESTAGIO_ACT: "Consumir",
    _ESTAGIO_CONVERT: "Contribuir",
}


def _frase_decisao(gargalo: str | None, convert_caindo: bool) -> str:
    """Frase de decisão -- SEMPRE linguagem associativa, nunca causal
    ("associado a"/"está relacionado a", nunca "causa"/"gera" -- issue #114,
    user story 8, hard requirement)."""
    if gargalo is None and not convert_caindo:
        return (
            "Ainda não há dado suficiente nos estágios com número real "
            "(Visualizações, curtidas, comentários) para identificar um "
            "gargalo nesta execução."
        )

    frases = []
    if gargalo == _ESTAGIO_ACT:
        frases.append(
            "muita gente vê os Reels, mas relativamente poucas curtidas "
            "estão associadas a essas visualizações -- possível gargalo "
            "em Consumir"
        )
    elif gargalo == _ESTAGIO_CONVERT:
        frases.append(
            "muita gente curte, mas poucos comentários positivos estão "
            "associados a essas curtidas -- possível gargalo em Contribuir"
        )
    if convert_caindo:
        frases.append(
            "o volume de comentários positivos está associado a uma queda "
            "vs. a execução anterior"
        )

    texto = "; ".join(frases)
    return texto[0].upper() + texto[1:] + "."


# ---------------------------------------------------------------------------
# Negatividade em alta (para a ação recomendada -- ver docstring do módulo,
# decisão 8). Mesma lógica de `resumo.py`/`radar.py`, duplicada aqui pelo
# mesmo raciocínio de autocontenção.
# ---------------------------------------------------------------------------


def _proporcao_negativo(df_sentiment_governador: pd.DataFrame) -> float | None:
    if (
        df_sentiment_governador.empty
        or "sentiment_label" not in df_sentiment_governador.columns
    ):
        return None
    total = len(df_sentiment_governador)
    if total == 0:
        return None
    return (df_sentiment_governador["sentiment_label"] == "negative").sum() / total


def _proporcao_negativo_media_por_governador(
    df_sentiment_todos: pd.DataFrame,
) -> float | None:
    """Média simples (cada governador pesa igual) das proporções de
    negativos por governador (`_chave`). `None` sem dado."""
    if df_sentiment_todos.empty or not {"sentiment_label", "_chave"}.issubset(
        df_sentiment_todos.columns
    ):
        return None
    por_gov = df_sentiment_todos.groupby("_chave")["sentiment_label"].apply(
        lambda s: (s == "negative").mean()
    )
    return float(por_gov.mean()) if not por_gov.empty else None


def _agregar_pct_negativo_por_run(
    df_sentiment_history_governador: pd.DataFrame, todos: bool = False
) -> pd.DataFrame:
    colunas = ["_chave", "_run_id", "pct_negativo"]
    required = {"sentiment_label", "_run_id"}
    if df_sentiment_history_governador.empty or not required.issubset(
        df_sentiment_history_governador.columns
    ):
        return pd.DataFrame(columns=colunas)

    if todos and "_chave" in df_sentiment_history_governador.columns:
        agregado = (
            df_sentiment_history_governador.groupby(["_run_id", "_chave"])[
                "sentiment_label"
            ]
            .apply(lambda s: (s == "negative").mean())
            .groupby("_run_id")
            .mean()
            .rename("pct_negativo")
            .reset_index()
        )
    else:
        agregado = (
            df_sentiment_history_governador.groupby("_run_id")["sentiment_label"]
            .apply(lambda s: (s == "negative").mean())
            .rename("pct_negativo")
            .reset_index()
        )
    agregado["_chave"] = _CHAVE_GOVERNADOR_UNICO
    return agregado[colunas]


def _delta_negativo(df_agregado_negativo: pd.DataFrame) -> float | None:
    if df_agregado_negativo.empty:
        return None
    resultado = week_over_week(
        df_agregado_negativo,
        value_col="pct_negativo",
        key_col="_chave",
        run_col="_run_id",
    )
    if not resultado:
        return None
    _, delta = resultado.get(_CHAVE_GOVERNADOR_UNICO, (None, None))
    return delta


def _negatividade_em_alta(
    pct_negativo_atual: float | None,
    delta_percentual: float | None,
    limiar: float = LIMIAR_NEGATIVIDADE_ALERTA,
) -> bool:
    """`True` se a negatividade atual cruzou o limiar de alerta OU subiu vs.
    a execução anterior -- mesmo critério de `radar.py::_nivel_semaforo`
    (danger/warn), reaproveitado aqui só para decidir a AÇÃO recomendada
    (não a cor da faixa desta tela, que segue `_nivel_decisao`)."""
    acima_do_limiar = (
        pct_negativo_atual is not None
        and not pd.isna(pct_negativo_atual)
        and pct_negativo_atual >= limiar
    )
    subiu = (
        delta_percentual is not None
        and not pd.isna(delta_percentual)
        and delta_percentual > 0
    )
    return bool(acima_do_limiar or subiu)


# ---------------------------------------------------------------------------
# Ação recomendada -- ver docstring do módulo, decisões 8-9.
# ---------------------------------------------------------------------------


def _acao_recomendada(gargalo: str | None, negatividade_em_alta: bool) -> dict | None:
    """Mapeia o diagnóstico desta tela para uma ação concreta: texto +
    tela-alvo (issue #114, user story 6). Negatividade em alta tem
    prioridade sobre o gargalo do funil (ver docstring do módulo, decisão
    8). `None` só quando não há gargalo identificável E a negatividade não
    está em alta -- nada de concreto para recomendar ainda."""
    if negatividade_em_alta:
        return {
            "texto": (
                "A negatividade recente dos comentários está associada a "
                "uma alta vs. a execução anterior (ou já cruzou o limite de "
                "alerta) -- vale investigar antes de agir sobre o funil."
            ),
            "alvo": _ACAO_RADAR,
            "label_botao": f"Ver {_LABEL_TELA_RADAR}",
        }
    if gargalo in (_ESTAGIO_ACT, _ESTAGIO_CONVERT):
        return {
            "texto": (
                f"O gargalo identificado em {_NOMES_GARGALO[gargalo]} está "
                "relacionado ao formato/tema do conteúdo produzido -- vale "
                "revisar a fila de pautas priorizadas e os formatos de Reel."
            ),
            "alvo": _ACAO_PRODUZIR,
            "label_botao": f"Ver {_LABEL_TELA_PRODUZIR}",
        }
    return None


def _navegar_para(tela: str) -> None:
    """Callback `on_click` do botão de ação -- ver docstring do módulo,
    decisão 9. PRECISA rodar como callback, nunca inline no corpo do
    script: `app.py` já instanciou o `st.radio` (mesma `key`,
    `tela_selecionada`) antes de chamar `render()`, e o Streamlit proíbe
    escrever no `session_state` de uma `key` de widget já instanciada
    na mesma execução (`StreamlitAPIException`). Um callback `on_click`
    roda antes do próximo rerun recriar o widget, o que é permitido."""
    st.session_state["tela_selecionada"] = tela


# ---------------------------------------------------------------------------
# Renderização (visual fiel ao protótipo do Funil -- issue #183)
# ---------------------------------------------------------------------------

# Tokens de cor de dado por estágio: (claro, escuro). Validados com o
# validador da skill `dataviz` (superfícies #fcfcfb / #1a1a19): Reach/Act
# (azul / azul mais escuro) separados por Delta E 20 (claro) e 22 (escuro) em
# visão normal; âmbar tem contraste < 3:1 no claro, compensado por valor e
# nome do estágio sempre visíveis em texto (rótulo direto em toda barra).
# Separados do vermelho IESB (chrome) -- o vermelho aqui só aparece como
# "perda" semântica, via token próprio.
CORES_ESTAGIO: dict[str, tuple[str, str]] = {
    _ESTAGIO_REACH: ("#2a78d6", "#5a9df0"),
    _ESTAGIO_ACT: ("#124080", "#2557a8"),
    _ESTAGIO_CONVERT: ("#eda100", "#c98500"),
    _ESTAGIO_ENGAGE: ("#008300", "#008300"),
}
# Texto sobre cada etapa (claro, escuro): contraste com o preenchimento do
# estágio nos dois temas (azul claro do escuro pede texto escuro).
_COR_TEXTO_ESTAGIO: dict[str, tuple[str, str]] = {
    _ESTAGIO_REACH: ("#ffffff", "#0b1220"),
    _ESTAGIO_ACT: ("#ffffff", "#ffffff"),
    _ESTAGIO_CONVERT: ("#1a1a19", "#1a1a19"),
}
# Selo de conversão entre etapas: (fundo, texto) no claro e no escuro.
_COR_SELO = (("#fcfcfb", "#1a1a19"), ("#1a1a19", "#f2f2f0"))

_ALTURA_ETAPA = 120
_ALTURA_ULTIMA_ETAPA = 84
_LARGURA_MIN_PCT = 14.0


def _css_vars(indice: int) -> str:
    return (
        f"--f-reach: {CORES_ESTAGIO[_ESTAGIO_REACH][indice]};"
        f"--f-act: {CORES_ESTAGIO[_ESTAGIO_ACT][indice]};"
        f"--f-convert: {CORES_ESTAGIO[_ESTAGIO_CONVERT][indice]};"
        f"--f-engage: {CORES_ESTAGIO[_ESTAGIO_ENGAGE][indice]};"
        f"--on-reach: {_COR_TEXTO_ESTAGIO[_ESTAGIO_REACH][indice]};"
        f"--on-act: {_COR_TEXTO_ESTAGIO[_ESTAGIO_ACT][indice]};"
        f"--on-convert: {_COR_TEXTO_ESTAGIO[_ESTAGIO_CONVERT][indice]};"
        f"--f-pill-bg: {_COR_SELO[indice][0]};"
        f"--f-pill-fg: {_COR_SELO[indice][1]};"
    )


_CSS_FUNIL = (
    "<style>"
    f".funil-viz {{ {_css_vars(0)} --f-track: rgba(128,128,128,.18); }}"
    "@media (prefers-color-scheme: dark) {"
    f' :root:where(:not([data-theme="light"])) .funil-viz {{ {_css_vars(1)} }} }}'
    f':root[data-theme="dark"] .funil-viz {{ {_css_vars(1)} }}'
    """
.funil-viz .f-stage { position:absolute; left:0; right:0; text-align:center; line-height:1.15;
  transform:translateY(-50%); pointer-events:none; white-space:nowrap; }
.funil-viz .f-stage i { display:block; font-size:11px; font-style:normal; font-weight:600;
  letter-spacing:.02em; }
.funil-viz .f-stage b { display:block; font-size:15px; }
.funil-viz .f-stage span { display:block; font-size:11px; font-weight:600; margin-top:2px; }
.funil-viz .f-pill { position:absolute; left:50%; transform:translate(-50%,-50%);
  background:var(--f-pill-bg); color:var(--f-pill-fg); border:1px solid rgba(128,128,128,.55);
  border-radius:10px; padding:4px 12px; text-align:center; white-space:nowrap;
  box-shadow:0 1px 3px rgba(0,0,0,.25); font-size:13px; font-weight:600; }
.funil-viz .f-badge { font-size:11px; border-radius:6px; padding:1px 8px; margin-left:8px;
  border:1px solid currentColor; font-weight:400; }
.funil-viz .f-pill-flow { text-align:center; margin:10px 0 0; }
.funil-viz .f-pill-flow .f-pill { position:static; transform:none; display:inline-block; }
.funil-viz .f-engage-card { border:2px dashed var(--f-engage); border-radius:10px;
  padding:10px 16px; margin:12px auto 0; max-width:420px; text-align:center; }
.funil-viz .f-engage-card i { font-style:normal; font-size:12px; font-weight:600; }
.funil-viz .f-engage-card b { display:block; font-size:18px; margin:2px 0; }
.funil-viz .f-engage-card small { display:block; font-size:11px; opacity:.7; }
.funil-viz .f-legenda { font-size:11px; opacity:.65; margin-top:8px; }
.funil-viz .f-card { border: 1px solid var(--f-track); border-left: 4px solid var(--f-convert);
  border-radius: 8px; padding: 12px 16px; margin: 14px 0; }
.funil-viz .f-card-title { font-size: 12px; opacity: .7; margin-bottom: 4px; }
</style>"""
)


def _larguras_log(valores: tuple[float, ...]) -> list[float | None]:
    """Largura (%) de cada etapa proporcional ao log10 do valor, relativa à
    maior, com mínimo `_LARGURA_MIN_PCT` para a etapa com dado ficar visível.
    `None` = sem dado (valor <= 0)."""
    logs = [math.log10(v) if v > 1 else (0.0 if v > 0 else None) for v in valores]
    topo = max((x for x in logs if x is not None), default=0.0)
    if topo <= 0:
        return [100.0 if x is not None else None for x in logs]
    return [None if x is None else max(_LARGURA_MIN_PCT, x / topo * 100) for x in logs]


def _fmt_dif(dif: float) -> str:
    return f"{'▲' if dif >= 0 else '▼'} {abs(dif) * 100:.0f}%"


def _fmt_taxa_pct(taxa: float) -> str:
    """Taxa (0-1) -> % com 2 algarismos significativos (20% / 8,6% / 0,036%)."""
    p = taxa * 100
    casas = 0 if p >= 10 else (1 if p >= 1 else (2 if p >= 0.1 else 3))
    return f"{p:.{casas}f}".replace(".", ",") + "%"


def _texto_taxa(taxa: float | None, destino_tem_dado: bool) -> str:
    """Texto de um selo de conversão: `X% avançam`; acima de 100% (a etapa
    seguinte é maior que a anterior), `N× a etapa anterior`."""
    if not destino_tem_dado or taxa is None:
        return "sem dado"
    if taxa <= 0:
        return "▼ nenhum avança"
    if taxa > 1:
        return f"▲ {taxa:.1f}× a etapa anterior".replace(".", ",")
    return f"▼ {_fmt_taxa_pct(taxa)} avançam"


def _html_selo_conversao(
    y: float, taxa: float | None, destino_tem_dado: bool, gargalo: bool
) -> str:
    """Selo de conversão centrado na fronteira entre duas etapas (`y` em px)."""
    corpo = _texto_taxa(taxa, destino_tem_dado)
    selo = '<span class="f-badge">gargalo</span>' if gargalo else ""
    return f'<div class="f-pill" style="top:{y:.0f}px">{corpo}{selo}</div>'


def _html_engage(engage: float, dif: float | None, is_todos: bool) -> str:
    """Bloco do Engage·Criar, separado do funil (ver docstring, decisão 4):
    quantidade de posts de UGC orgânico, em uma frase objetiva."""
    if engage <= 0:
        valor = "sem dado"
        detalhe = "nenhum post de UGC orgânico coletado para este governador"
    else:
        valor = _fmt_int_br(engage) + (f" · {_fmt_dif(dif)}" if dif is not None else "")
        detalhe = (
            "média de posts de UGC orgânico por governador"
            if is_todos
            else "posts de UGC orgânico: conteúdos de terceiros, não pagos, que "
            "mencionam o governador"
        )
    return (
        '<div class="f-engage-card"><i>Engage · Criar</i>'
        f"<b>{valor}</b><small>{detalhe}</small></div>"
    )


def _html_funil(
    estagios: tuple[float, float, float],
    taxas: dict,
    gargalo: str | None,
    engage: float = 0.0,
    comparativos: dict | None = None,
    is_todos: bool = False,
) -> str:
    """Funil de 3 etapas (trapézios contínuos, largura em escala log): título e
    valor dentro de cada etapa (com ▲/▼ + diferença vs. a mediana dos demais
    quando há `comparativos`), selo de conversão entre as etapas e, abaixo, o
    selo Convert -> Engage e o bloco do Engage. Ver docstring do módulo, decisões 4 e 10."""
    dif = (comparativos or {}).get("dif", {})
    larguras = [w if w is not None else 0.0 for w in _larguras_log(estagios)]
    bases = larguras[1:] + [larguras[-1] * 0.8]
    alturas = [_ALTURA_ETAPA, _ALTURA_ETAPA, _ALTURA_ULTIMA_ETAPA]
    total_h = sum(alturas)
    nomes = [
        (_ESTAGIO_REACH, "Reach", estagios[0]),
        (_ESTAGIO_ACT, "Act", estagios[1]),
        (_ESTAGIO_CONVERT, "Convert", estagios[2]),
    ]
    formas: list[str] = []
    rotulos: list[str] = []
    fronteiras: list[float] = []
    y = 0.0
    for i, (chave, nome, valor) in enumerate(nomes):
        topo, base = larguras[i], bases[i]
        if valor > 0 and topo > 0:
            x1, x2 = (100 - topo) / 2, (100 + topo) / 2
            x3, x4 = (100 + base) / 2, (100 - base) / 2
            formas.append(
                f'<polygon points="{x1:.2f},{y:.1f} {x2:.2f},{y:.1f} '
                f'{x3:.2f},{y + alturas[i]:.1f} {x4:.2f},{y + alturas[i]:.1f}" '
                f'style="fill:var(--f-{chave})" />'
            )
            comparativo = f"<span>{_fmt_dif(dif[chave])}</span>" if chave in dif else ""
            frac = 0.38 if i < 2 else 0.55
            rotulos.append(
                f'<div class="f-stage" style="top:{y + alturas[i] * frac:.0f}px;'
                f'color:var(--on-{chave})"><i>{nome}</i>'
                f"<b>{_fmt_int_br(valor)}</b>{comparativo}</div>"
            )
        else:
            formas.append(
                f'<rect x="35" y="{y + 6:.1f}" width="30" height="{alturas[i] - 12:.1f}" '
                'style="fill:none;stroke:var(--f-track);stroke-width:.6;'
                'stroke-dasharray:2 1.5" />'
            )
            rotulos.append(
                f'<div class="f-stage" style="top:{y + alturas[i] * 0.5:.0f}px;opacity:.7">'
                f"<i>{nome}</i><span>sem dado</span></div>"
            )
        y += alturas[i]
        if i < 2:
            fronteiras.append(y)
    selos = [
        _html_selo_conversao(
            fronteiras[0], taxas["act"], estagios[1] > 0, gargalo == _ESTAGIO_ACT
        ),
        _html_selo_conversao(
            fronteiras[1],
            taxas["convert"],
            estagios[2] > 0,
            gargalo == _ESTAGIO_CONVERT,
        ),
    ]
    svg = (
        f'<svg viewBox="0 0 100 {total_h}" preserveAspectRatio="none" '
        f'style="width:100%;height:{total_h}px;display:block">'
        + "".join(formas)
        + "</svg>"
    )
    if comparativos:
        legenda = (
            "Entre as etapas: quanto avança. Dentro: ▲/▼ = diferença relativa do valor "
            f"vs. a mediana dos demais governadores (n = {comparativos['n']}). "
        )
    else:
        legenda = (
            "Entre as etapas: quanto avança. A comparação com a mediana dos demais "
            "governadores aparece ao selecionar um governador. "
        )
    legenda += (
        "Largura em escala logarítmica: cada degrau equivale a uma ordem de "
        "grandeza, não ao volume proporcional."
    )
    selo_engage = _texto_taxa(
        _taxa_engage(estagios[2], engage), estagios[2] > 0 and engage > 0
    )
    return (
        '<div class="funil-viz">'
        '<div style="max-width:620px;margin:0 auto;position:relative">'
        f"{svg}{''.join(rotulos)}{''.join(selos)}</div>"
        f'<div class="f-pill-flow"><div class="f-pill">{selo_engage}</div></div>'
        + _html_engage(engage, dif.get(_ESTAGIO_ENGAGE), is_todos)
        + f'<div class="f-legenda">{legenda}</div></div>'
    )


def _texto_como_ler(is_todos: bool) -> str:
    """Markdown do expander "Como ler este funil": o que cada etapa mede e
    como interpretar os números da visualização."""
    escopo = (
        "Em **Todos os Governadores**, cada etapa é a **média por governador** e "
        'não há comparação (não existem "demais").'
        if is_todos
        else "Com um governador selecionado, cada etapa mostra **▲/▼ e um %**: a "
        "diferença do valor dele contra a **mediana dos demais governadores**."
    )
    return (
        "**O que cada etapa mede**\n"
        "- **Reach · Alcançar:** visualizações. Soma das reproduções dos Reels do "
        "governador.\n"
        "- **Act · Consumir:** curtidas. Total de curtidas do perfil.\n"
        "- **Convert · Contribuir:** comentários positivos. Quantos comentários "
        "foram classificados como positivos.\n"
        "- **Engage · Criar:** posts de UGC orgânico. Conteúdos publicados por "
        "terceiros, sem pagamento, que mencionam o governador.\n\n"
        "**Como interpretar os números**\n"
        "- **Largura do funil:** escala logarítmica. Cada degrau equivale a uma "
        "ordem de grandeza (10×), não ao volume proporcional. Leia o número "
        "dentro da etapa.\n"
        '- **Selo "X% avançam":** a etapa de baixo dividida pela de cima. '
        '"5,3% avançam" entre Reach e Act significa 5,3 curtidas a cada 100 '
        "visualizações. As unidades mudam a cada etapa, então é uma razão entre "
        "grandezas diferentes, não a fração de pessoas que avançou.\n"
        "- **Gargalo:** a menor taxa entre Reach→Act e Act→Convert. "
        "Convert→Engage aparece, mas não entra no gargalo (compara comentários "
        "com posts de terceiros).\n"
        f"- **Setas dentro das etapas:** {escopo} Isso mostra **tamanho** "
        "(escala do perfil), não eficiência. Para eficiência, olhe os selos de "
        "taxa.\n\n"
        "**Cuidados**\n"
        "- Act é do perfil inteiro, enquanto Reach conta só Reels: a taxa "
        "Reach→Act é uma aproximação.\n"
        "- Engage depende da coleta de UGC e hoje vem de uma amostra de teste; "
        "a taxa Convert→Engage reflete essa amostra."
    )


def render(governor_url: str) -> None:
    """Sub-aba Funil para `governor_url` (URL real ou
    `TODOS_OS_GOVERNADORES` -> média por governador)."""
    is_todos = governor_url == TODOS_OS_GOVERNADORES

    # ---- Dado bruto ----
    df_clusters = data.load_clusters_content()
    df_reels = data.load_reels_content()
    df_engagement = data.load_engagement()
    df_sentiment = data.comments_only(data.load_sentiment())
    df_sentiment_history = data.comments_only(data.load_sentiment_history())
    df_ugc = data.load_ugc_mentions()
    if not df_sentiment.empty and "inputUrl" in df_sentiment.columns:
        df_sentiment = df_sentiment.assign(
            _chave=_normalize_url(df_sentiment["inputUrl"])
        )
    if not df_sentiment_history.empty and "inputUrl" in df_sentiment_history.columns:
        df_sentiment_history = df_sentiment_history.assign(
            _chave=_normalize_url(df_sentiment_history["inputUrl"])
        )

    # ---- Estágios com dado real (média por governador em "Todos") ----
    estagios = _estagios_para_selecao(
        governor_url, df_clusters, df_reels, df_engagement, df_sentiment
    )

    # ---- Engage (UGC do piloto) + comparativo vs. mediana dos demais ----
    engage = _engage_para_selecao(governor_url, df_ugc)
    piloto = _ugc_e_amostra_piloto(df_ugc)
    valores_comparativo = {
        _ESTAGIO_REACH: estagios[0],
        _ESTAGIO_ACT: estagios[1],
        _ESTAGIO_CONVERT: estagios[2],
    }
    if not piloto:  # com o teto do piloto, comparar contagens é ruído
        valores_comparativo[_ESTAGIO_ENGAGE] = engage
    comparativos = _diferencas_vs_mediana(
        valores_comparativo,
        _estagios_com_engage_por_governador(
            df_clusters, df_reels, df_engagement, df_sentiment, df_ugc
        ),
        governor_url,
    )

    # ---- Taxas de passagem + gargalo ----
    taxas = _taxas_passagem(*estagios)
    gargalo = _identificar_gargalo(taxas)

    # ---- Escalonamento (Convert caindo) e negatividade em alta ----
    if is_todos:
        df_hist = df_sentiment_history
        pct_negativo_atual = _proporcao_negativo_media_por_governador(df_sentiment)
    else:
        df_hist = _filtrar_por_governador(df_sentiment_history, governor_url)
        pct_negativo_atual = _proporcao_negativo(
            _filtrar_por_governador(df_sentiment, governor_url)
        )
    convert_caindo = _convert_esta_caindo(
        _agregar_positivos_por_run(df_hist, todos=is_todos)
    )
    delta_negativo = _delta_negativo(
        _agregar_pct_negativo_por_run(df_hist, todos=is_todos)
    )
    negatividade_em_alta = _negatividade_em_alta(pct_negativo_atual, delta_negativo)

    # ---- Título + funil ----
    st.markdown("#### Funil de Engajamento COBRA-RACE")
    st.caption(
        "Das visualizações à criação: onde a audiência 'trava' entre ver, curtir, "
        "comentar positivamente e criar conteúdo próprio."
        + (
            " Em Todos os Governadores, cada estágio é a média por governador."
            if is_todos
            else ""
        )
    )
    st.markdown(
        _CSS_FUNIL
        + _html_funil(
            estagios,
            taxas,
            gargalo,
            engage=engage,
            comparativos=comparativos,
            is_todos=is_todos,
        ),
        unsafe_allow_html=True,
    )
    with st.expander("Como ler este funil"):
        st.markdown(_texto_como_ler(is_todos))

    # ---- Leitura automática para a assessoria ----
    nivel = _nivel_decisao(gargalo, convert_caindo)
    cor_borda = COLORS[nivel]["fg"]
    acao = _acao_recomendada(gargalo, negatividade_em_alta)
    st.markdown(
        '<div class="funil-viz"><div class="f-card" '
        f'style="border-left-color:{cor_borda};">'
        '<div class="f-card-title">Leitura automática para a assessoria</div>'
        f"<div>{_frase_decisao(gargalo, convert_caindo)}</div>"
        + (f'<div style="margin-top:6px;">{acao["texto"]}</div>' if acao else "")
        + "</div></div>",
        unsafe_allow_html=True,
    )
    if acao is None:
        st.caption("Ainda não há dado suficiente para recomendar uma ação concreta.")
    else:
        # `on_click` (não `if st.button`): escrita válida em `session_state`
        # de uma `key` de widget já instanciada -- ver `_navegar_para`.
        alvo = (
            _LABEL_TELA_RADAR if acao["alvo"] == _ACAO_RADAR else _LABEL_TELA_PRODUZIR
        )
        st.button(
            acao["label_botao"],
            key="funil_acao_navegar",
            on_click=_navegar_para,
            args=(alvo,),
        )

    footnote(_NOTA_FUNIL)
