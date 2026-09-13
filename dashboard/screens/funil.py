"""Tela 6 -- "Funil de engajamento" (ADR 0021 / issue #114), a tela
carro-chefe do dashboard.

Responde à tese central do TCC (Cap. 6): o funil COBRA-RACE completo, dos 4
estágios (Reach·Alcançar -> Act·Consumir -> Convert·Contribuir ->
Engage·Criar), como 4 barras horizontais + taxas de passagem + gargalo +
ação recomendada. Substitui `pages/05_funil.py` (ADR 0020) -- ver ADR 0021,
"Opção C híbrida": esta tela é a "espinha conceitual" da ferramenta, e cada
uma das outras 5 telas carrega só um `stage_label()` discreto apontando para
o estágio correspondente.

Mesma estrutura de módulo das Telas 1-3 (ver `resumo.py`/`produzir.py`/
`radar.py`): funções puras nomeadas, testadas em
`tests/test_dashboard_screens_funil.py`; `render()` só orquestra I/O do
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
4. **Engage·Criar -- proibição estrutural de tabela `ugc_*`.** Este módulo
   NUNCA importa, chama ou referencia `governor_ugc_mentions`/
   `load_ugc_mentions`/`aggregate_ugc_by_governor` (nem qualquer identificador
   cujo nome comece com "ugc") -- a barra de Engage é 100% estática (texto
   fixo "em construção", sem nenhuma consulta a dado). Ver teste estático
   dedicado (`test_funil_module_never_references_ugc_tables`), que faz
   inspeção de AST do código-fonte deste módulo. `load_discourse_topics()`
   também NÃO é usado como proxy numérico disfarçado para Engage -- na
   dúvida, a issue pede para omitir o número, não arriscar parecer dado
   real.
5. **Taxas de passagem -- dado insuficiente é `None`, nunca zero.**
   `_taxas_passagem` só calcula uma taxa quando o estágio de origem tem
   valor real (> 0); do contrário retorna `None` para aquela taxa --
   `_identificar_gargalo` exclui candidatos `None` do cálculo, nunca os
   trata como "taxa de 0%" (que seria uma afirmação diferente e mais forte
   do que "não sei"). `Convert/Engage` nunca é uma chave calculada -- é
   sempre o texto fixo "sem dado real" em `render()`.
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
9. **Navegação -- `st.session_state`, não `st.page_link`.** `dashboard/app.py`
   (issue #110) usa `st.radio` (não multipágina nativa do Streamlit) para
   navegação. O botão de ação desta tela grava o rótulo da tela-alvo em
   `st.session_state["tela_selecionada"]` (a mesma `key` que `app.py` passou
   a usar no `st.radio`, ver `app.py`) e chama `st.rerun()` -- no próximo
   render, o `st.radio` lê o valor já setado em `session_state` como seleção
   inicial. Documentado também no PR desta issue.
10. **Texto sempre associativo, nunca causal.** Toda frase de decisão/ação
    usa "associado a"/"está relacionado a" -- nunca "causa"/"gera" no
    sentido causal (issue #114, user story 8, hard requirement de
    honestidade analítica para o TCC).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.core import data
from dashboard.core.components import decision_band, footnote, stage_label
from dashboard.core.deltas import LIMIAR_NEGATIVIDADE_ALERTA, week_over_week
from dashboard.core.theme import COLORS

_PLACEHOLDER_SEM_GOVERNADOR = "—"
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
    'Funil COBRA-RACE · "Criar" depende de menções de terceiros (piloto) · '
    "baseado em Reels."
)


# ---------------------------------------------------------------------------
# Normalização / seleção de governador (duplicado de `resumo.py`/`produzir.py`/
# `radar.py` -- mesmo raciocínio: cada tela fica autocontida, sem depender de
# outra tela nem de `src/dashboard/filters.py`, que está sendo descontinuado
# tela por tela pela ADR 0021).
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


def _fmt_int_br(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return _PLACEHOLDER_SEM_DADO
    return f"{int(round(valor)):,}".replace(",", ".")


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
    if "content_type" not in df_clusters.columns or "id_reel" not in df_clusters.columns:
        return 0.0

    clusters_reel = df_clusters[df_clusters["content_type"] == "reel"]
    if clusters_reel.empty:
        return 0.0

    reels_governador = _filtrar_por_governador(df_reels, governor_url)
    if reels_governador.empty or "id" not in reels_governador.columns:
        return 0.0
    if "videoPlayCount" not in reels_governador.columns:
        return 0.0

    merged = reels_governador.merge(clusters_reel, left_on="id", right_on="id_reel", how="inner")
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


# ---------------------------------------------------------------------------
# Taxas de passagem + identificação do gargalo -- ver docstring do módulo,
# decisões 5-6.
# ---------------------------------------------------------------------------


def _taxas_passagem(reach: float, act: float, convert: float) -> dict[str, float | None]:
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


def _agregar_positivos_por_run(df_sentiment_history_governador: pd.DataFrame) -> pd.DataFrame:
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
    if df_sentiment_governador.empty or "sentiment_label" not in df_sentiment_governador.columns:
        return None
    total = len(df_sentiment_governador)
    if total == 0:
        return None
    return (df_sentiment_governador["sentiment_label"] == "negative").sum() / total


def _agregar_pct_negativo_por_run(df_sentiment_history_governador: pd.DataFrame) -> pd.DataFrame:
    colunas = ["_chave", "_run_id", "pct_negativo"]
    required = {"sentiment_label", "_run_id"}
    if df_sentiment_history_governador.empty or not required.issubset(
        df_sentiment_history_governador.columns
    ):
        return pd.DataFrame(columns=colunas)

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
    if pct_negativo_atual is not None and not pd.isna(pct_negativo_atual):
        if pct_negativo_atual >= limiar:
            return True
    if delta_percentual is not None and not pd.isna(delta_percentual) and delta_percentual > 0:
        return True
    return False


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
                "revisar a fila de temas priorizados e os formatos de Reel."
            ),
            "alvo": _ACAO_PRODUZIR,
            "label_botao": f"Ver {_LABEL_TELA_PRODUZIR}",
        }
    return None


# ---------------------------------------------------------------------------
# Renderização de uma barra do funil (largura proporcional ao valor)
# ---------------------------------------------------------------------------


def _largura_barra_pct(valor: float, valor_maximo: float) -> float:
    if valor_maximo <= 0 or valor <= 0:
        return 0.0
    return min(100.0, max(2.0, (valor / valor_maximo) * 100.0))


def _render_barra_estagio(
    nome_estagio: str, rotulo_metrica: str, valor: float, valor_maximo: float, destaque: bool
) -> None:
    largura_pct = _largura_barra_pct(valor, valor_maximo)
    cor_fg = COLORS["warn"]["fg"] if destaque else COLORS["info"]["fg"]
    selo = (
        f'<span style="background:{COLORS["warn"]["fg"]};color:#fff;'
        'border-radius:6px;padding:1px 8px;font-size:11px;margin-left:8px;">'
        "gargalo</span>"
        if destaque
        else ""
    )
    st.markdown(
        f"""
        <div style="margin:10px 0;">
          <div style="font-size:13px;margin-bottom:4px;">
            <strong>{nome_estagio}</strong> · {rotulo_metrica}: {_fmt_int_br(valor)}{selo}
          </div>
          <div style="background:#EEECE3;border-radius:6px;height:22px;width:100%;">
            <div style="background:{cor_fg};width:{largura_pct:.1f}%;
                        height:22px;border-radius:6px;"></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_barra_engage() -> None:
    """Engage·Criar -- SEMPRE tracejada, SEMPRE "em construção", NUNCA um
    número (ver docstring do módulo, decisão 4). Nenhuma consulta a dado
    acontece aqui -- é texto estático."""
    st.markdown(
        """
        <div style="margin:10px 0;">
          <div style="font-size:13px;margin-bottom:4px;"><strong>Engage · Criar</strong></div>
          <div style="border:2px dashed #B9B7AC;border-radius:6px;height:22px;
                      width:100%;display:flex;align-items:center;
                      justify-content:center;color:#8A8879;font-size:12px;">
            em construção
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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
        stage_label("O funil completo")
        st.info(
            "Nenhum governador disponível ainda -- rode a pipeline "
            "(`uv run python pipeline.py`) para popular o dashboard."
        )
        footnote()
        footnote(_NOTA_FUNIL)
        return

    nome_selecionado = st.selectbox("Governador", options=list(options.keys()))
    governor_url = options[nome_selecionado]
    stage_label("O funil completo")

    # ---- Dado bruto ----
    df_clusters = data.load_clusters_content()
    df_reels = data.load_reels_content()
    df_sentiment_governador = data.comments_only(
        _filtrar_por_governador(data.load_sentiment(), governor_url)
    )
    df_sentiment_history_governador = data.comments_only(
        _filtrar_por_governador(data.load_sentiment_history(), governor_url)
    )

    # ---- Estágios com dado real ----
    reach = _visualizacoes_reels_governador(df_clusters, df_reels, governor_url)
    act = _consumir_likes_governador(df_engagement, governor_url)
    convert = _contribuir_comentarios_positivos_governador(df_sentiment_governador, governor_url)

    # ---- Taxas de passagem + gargalo ----
    taxas = _taxas_passagem(reach, act, convert)
    gargalo = _identificar_gargalo(taxas)

    # ---- Escalonamento (Convert caindo vs. execução anterior) ----
    df_positivos_hist = _agregar_positivos_por_run(df_sentiment_history_governador)
    convert_caindo = _convert_esta_caindo(df_positivos_hist)

    # ---- Negatividade em alta (para a ação recomendada) ----
    pct_negativo_atual = _proporcao_negativo(df_sentiment_governador)
    df_negativo_hist = _agregar_pct_negativo_por_run(df_sentiment_history_governador)
    delta_negativo = _delta_negativo(df_negativo_hist)
    negatividade_em_alta = _negatividade_em_alta(pct_negativo_atual, delta_negativo)

    # ---- Frase de decisão ----
    nivel = _nivel_decisao(gargalo, convert_caindo)
    decision_band(_frase_decisao(gargalo, convert_caindo), level=nivel)

    # ---- 4 barras do funil ----
    st.markdown("#### Funil COBRA-RACE")
    valor_maximo = max(reach, act, convert, 1.0)
    _render_barra_estagio(
        "Reach · Alcançar", "Visualizações", reach, valor_maximo, destaque=False
    )
    _render_barra_estagio(
        "Act · Consumir", "Curtidas", act, valor_maximo, destaque=gargalo == _ESTAGIO_ACT
    )
    _render_barra_estagio(
        "Convert · Contribuir",
        "Comentários positivos",
        convert,
        valor_maximo,
        destaque=gargalo == _ESTAGIO_CONVERT,
    )
    _render_barra_engage()

    # ---- Taxas de passagem ----
    st.markdown("#### Taxas de passagem")
    col1, col2, col3 = st.columns(3)
    col1.metric("Act / Reach", _fmt_pct(taxas[_ESTAGIO_ACT]))
    col2.metric("Convert / Act", _fmt_pct(taxas[_ESTAGIO_CONVERT]))
    col3.metric("Convert → Engage", "sem dado real")

    # ---- O que fazer ----
    st.markdown("#### O que fazer")
    acao = _acao_recomendada(gargalo, negatividade_em_alta)
    if acao is None:
        st.caption("Ainda não há dado suficiente para recomendar uma ação concreta.")
    else:
        st.write(acao["texto"])
        # Navegação via `st.session_state` -- ver docstring do módulo,
        # decisão 9. `dashboard/app.py` lê a mesma `key` no `st.radio`.
        if st.button(acao["label_botao"], key="funil_acao_navegar"):
            st.session_state["tela_selecionada"] = (
                _LABEL_TELA_RADAR if acao["alvo"] == _ACAO_RADAR else _LABEL_TELA_PRODUZIR
            )
            st.rerun()

    footnote()
    footnote(_NOTA_FUNIL)
