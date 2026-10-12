"""Sub-aba NSM do Resumo (ADR 0031 / issues #183 e #187).

Mostra os cartões de NSM (com a Tendência da proporção de comentários
positivos, ADR 0040 / issue #285 -- RASCUNHO PROVISÓRIO, método e limiares
aguardam o backtest #284),
melhor aprovação e maior rejeição e o contraste dos rankings completos (com
rolagem) por engajamento bruto x qualificado (NSM como índice 0-100).
A frase de decisão e as linhas de KPIs (incluindo Crescimento) que a sub-aba
herdou do Resumo foram removidas da sub-aba.

Toda a lógica vive em funções puras nomeadas abaixo, testadas em
`tests/test_dashboard_screens_resumo_nsm.py`; `render()` só orquestra I/O do
Streamlit sobre o resultado dessas funções.
"""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from dashboard.core import data
from dashboard.core.deltas import parse_publication_dates
from dashboard.core.tendencia import (
    CAINDO,
    ESTAVEL,
    INSUFICIENTE,
    SUBINDO,
    Tendencia,
    tendencia_conjunto,
    tendencia_proporcao,
)
from dashboard.screens.resumo_comum import (
    _PLACEHOLDER_SEM_GOVERNADOR,
    TODOS_OS_GOVERNADORES,
    _normalize_url,
)

# ---------------------------------------------------------------------------
# Formatação (arredondamento no ponto de exibição -- issue #111, user story 11)
# ---------------------------------------------------------------------------


def _fmt_pct(valor: float | None) -> str:
    """Fração (0-1) -> string de porcentagem com 1 casa decimal. Nunca exibe
    o float bruto (ex.: "71.428571%")."""
    if valor is None or pd.isna(valor):
        return _PLACEHOLDER_SEM_GOVERNADOR
    return f"{valor * 100:.1f}%"


def _fmt_int_br(valor: float | None) -> str:
    """Inteiro com separador de milhar `.` (pt-BR) -- usado para seguidores."""
    if valor is None or pd.isna(valor):
        return _PLACEHOLDER_SEM_GOVERNADOR
    return f"{int(valor):,}".replace(",", ".")


# ---------------------------------------------------------------------------
# Contraste de rankings bruto x NSM (issue #187)
#
# "Engajamento bruto" = `total_engajamento` de `governor_nsm` (volume total de
# curtidas + comentarios por perfil, a mesma coluna-fonte `TOTAL ENGAJAMENTO`
# de `governor_engagement`). A medida exata usada na verificacao da ADR 0020
# nao e identificavel com seguranca (o texto da ADR cita "volume bruto"); o
# volume total e a leitura direta. Contra o dado de 2026-10-04 o ranking por
# NSM diverge desse bruto em 20 de 26 perfis.
#
# O NSM de `governor_nsm` e uma razao sem teto (proporcao positiva x alcance
# medio); para exibi-lo de 0 a 100 aplicamos min-max entre os perfis com NSM
# (mesma normalizacao do Scorecard, ADR 0030): 100 = lider, 0 = ultimo.
# ---------------------------------------------------------------------------

ETIQUETA_SUBIU = "SUBIU"
ETIQUETA_CAIU = "CAIU"


def _indice_nsm_0_100(nsm: pd.Series) -> pd.Series:
    """NSM bruto -> 0-100 por min-max entre os perfis com valor. Todos
    iguais (ou so um perfil) -> 100 para quem tem valor; `NaN` preservado."""
    validos = nsm.dropna()
    if validos.empty:
        return nsm.astype(float)
    menor, maior = validos.min(), validos.max()
    if maior == menor:
        return nsm.where(nsm.isna(), 100.0).astype(float)
    return (nsm - menor) / (maior - menor) * 100.0


# Mínimo de comentários para um perfil disputar "Melhor aprovação" e "Maior
# rejeição": com poucos comentários, 3 de 3 positivos viraria 100% (ADR 0038).
MIN_COMENTARIOS_CARTAO = 30


def montar_tabela_contraste(
    df_nsm: pd.DataFrame,
    df_comentarios: pd.DataFrame,
    df_metadata: pd.DataFrame,
) -> pd.DataFrame:
    """Uma linha por perfil de `governor_nsm`, colunas `chave`, `nome`,
    `bruto`, `nsm` (0-100, `NaN` = perfil sem NSM), `pct_pos`, `pct_neg`
    (fracoes 0-1 dos comentarios; `NaN` sem comentarios). Vazio (com as
    colunas) se `df_nsm` estiver vazio ou sem as colunas esperadas."""
    colunas = ["chave", "nome", "bruto", "nsm", "pct_pos", "pct_neg", "n_comentarios"]
    if df_nsm.empty or not {"inputUrl", "nsm"}.issubset(df_nsm.columns):
        return pd.DataFrame(columns=colunas)

    nan = pd.Series(float("nan"), index=df_nsm.index)
    tabela = pd.DataFrame(
        {
            "chave": _normalize_url(df_nsm["inputUrl"]),
            "nome": df_nsm["username"] if "username" in df_nsm.columns else nan,
            "bruto": (
                df_nsm["total_engajamento"].astype(float)
                if "total_engajamento" in df_nsm.columns
                else nan
            ),
            "nsm": _indice_nsm_0_100(df_nsm["nsm"].astype(float)),
        }
    )

    if not df_metadata.empty and {"inputUrl", "nome"}.issubset(df_metadata.columns):
        nomes = dict(
            zip(
                _normalize_url(df_metadata["inputUrl"]),
                df_metadata["nome"],
                strict=True,
            )
        )
        tabela["nome"] = [
            nomes[c] if isinstance(nomes.get(c), str) and nomes[c] else n
            for c, n in zip(tabela["chave"], tabela["nome"], strict=True)
        ]
    tabela["nome"] = tabela["nome"].fillna(tabela["chave"]).astype(str)

    for coluna, label in (("pct_pos", "positive"), ("pct_neg", "negative")):
        tabela[coluna] = float("nan")
        if not df_comentarios.empty and {"inputUrl", "sentiment_label"}.issubset(
            df_comentarios.columns
        ):
            chaves = _normalize_url(df_comentarios["inputUrl"])
            frac = (df_comentarios["sentiment_label"] == label).groupby(chaves).mean()
            tabela[coluna] = tabela["chave"].map(frac)
    tabela["n_comentarios"] = 0
    if not df_comentarios.empty and "inputUrl" in df_comentarios.columns:
        contagem = _normalize_url(df_comentarios["inputUrl"]).value_counts()
        tabela["n_comentarios"] = tabela["chave"].map(contagem).fillna(0).astype(int)
    # `linhas_ranking` indexa por `chave`: defensivo contra URL repetida.
    return (tabela[colunas].drop_duplicates(subset="chave", keep="first")).reset_index(
        drop=True
    )


def extremo(
    tabela: pd.DataFrame, coluna: str, maior: bool = True
) -> tuple[str, float] | None:
    """`(nome, valor)` do perfil de maior (ou menor) `coluna`; empate decidido
    pelo nome em ordem alfabetica (deterministico). `None` se nao ha valor."""
    if tabela.empty or coluna not in tabela.columns:
        return None
    validos = tabela.dropna(subset=[coluna])
    if validos.empty:
        return None
    ordenado = validos.sort_values(
        [coluna, "nome"], ascending=[not maior, True], kind="mergesort"
    )
    linha = ordenado.iloc[0]
    return str(linha["nome"]), float(linha[coluna])


def extremo_com_amostra(
    tabela: pd.DataFrame, coluna: str, minimo: int = MIN_COMENTARIOS_CARTAO
) -> tuple[str, float, int] | None:
    """Como `extremo` (maior `coluna`), mas só entre perfis com pelo menos
    `minimo` comentários, e devolve também o nº de comentários. Evita que um
    perfil com 3 comentários vire "melhor aprovação 100%". `None` se nenhum
    perfil atinge o mínimo."""
    if tabela.empty or not {coluna, "n_comentarios"}.issubset(tabela.columns):
        return None
    elegiveis = tabela[tabela["n_comentarios"] >= minimo].dropna(subset=[coluna])
    if elegiveis.empty:
        return None
    linha = elegiveis.sort_values(
        [coluna, "nome"], ascending=[False, True], kind="mergesort"
    ).iloc[0]
    return str(linha["nome"]), float(linha[coluna]), int(linha["n_comentarios"])


def posicoes(tabela: pd.DataFrame, coluna: str) -> dict[str, int]:
    """`{chave: posicao}` (1 = maior `coluna`) no ranking COMPLETO; empates
    desempatados pelo nome. Perfis sem valor ficam de fora."""
    if tabela.empty or coluna not in tabela.columns:
        return {}
    validos = tabela.dropna(subset=[coluna]).sort_values(
        [coluna, "nome"], ascending=[False, True], kind="mergesort"
    )
    return {chave: i for i, chave in enumerate(validos["chave"], start=1)}


def etiqueta_mudanca(pos_bruto: int | None, pos_nsm: int | None) -> str | None:
    """`SUBIU` se a posicao no ranking por NSM e melhor (menor) que no bruto,
    `CAIU` se pior, `None` se igual ou se faltar uma das posicoes."""
    if pos_bruto is None or pos_nsm is None or pos_bruto == pos_nsm:
        return None
    return ETIQUETA_SUBIU if pos_nsm < pos_bruto else ETIQUETA_CAIU


def linhas_ranking(
    tabela: pd.DataFrame,
    coluna: str,
    chave_selecionada: str | None,
    com_etiqueta: bool = False,
) -> list[dict]:
    """Linhas do ranking COMPLETO por `coluna` (todos os perfis com valor),
    em ordem de posicao; o governador selecionado (`chave_selecionada`,
    `None` = "Todos") vem marcado em `selecionado`. Cada linha: `posicao`,
    `nome`, `valor`, `selecionado`, `etiqueta`. A etiqueta SUBIU/CAIU (so
    com `com_etiqueta=True`) compara as posicoes nos rankings completos por
    `bruto` e `nsm`."""
    pos = posicoes(tabela, coluna)
    if not pos:
        return []
    pos_bruto = posicoes(tabela, "bruto")
    pos_nsm = posicoes(tabela, "nsm")
    por_chave = tabela.set_index("chave")

    def linha(chave: str) -> dict:
        reg = por_chave.loc[chave]
        return {
            "posicao": pos[chave],
            "nome": str(reg["nome"]),
            "valor": float(reg[coluna]),
            "selecionado": chave == chave_selecionada,
            "etiqueta": (
                etiqueta_mudanca(pos_bruto.get(chave), pos_nsm.get(chave))
                if com_etiqueta
                else None
            ),
        }

    return [linha(c) for c in sorted(pos, key=pos.__getitem__)]


def valor_cartao_nsm(
    tabela: pd.DataFrame, chave_selecionada: str | None
) -> float | None:
    """NSM (0-100) do selecionado, ou a media simples dos perfis com NSM em
    "Todos" (`chave_selecionada=None`). `None` sem dado."""
    if tabela.empty or "nsm" not in tabela.columns:
        return None
    if chave_selecionada is None:
        serie = tabela["nsm"].dropna()
        return float(serie.mean()) if not serie.empty else None
    linha = tabela[tabela["chave"] == chave_selecionada]["nsm"].dropna()
    return float(linha.iloc[0]) if not linha.empty else None


def series_sentimento_por_dia(df_comentarios: pd.DataFrame) -> pd.DataFrame:
    """Série BRUTA de comentários por perfil, data e formato: colunas `chave`,
    `data`, `formato` (`origem_comentario`: reel/post; "?" se ausente),
    `positivos` e `total`. Nunca usa o índice 0-100 min-máx do NSM.

    Limitação (rascunho): a data é a do COMENTÁRIO (`timestamp` de
    `governor_sentiment`), não a da publicação comentada -- a Gold de
    sentimento não traz a data do post/reel. Decisão do autor pendente."""
    colunas = ["chave", "data", "formato", "positivos", "total"]
    if df_comentarios.empty or not {
        "inputUrl",
        "timestamp",
        "sentiment_label",
    }.issubset(df_comentarios.columns):
        return pd.DataFrame(columns=colunas)
    df = df_comentarios
    if "id_comment" in df.columns:
        df = df.drop_duplicates(subset=["id_comment"], keep="first")
    formato = (
        df["origem_comentario"].fillna("?")
        if "origem_comentario" in df.columns
        else pd.Series("?", index=df.index)
    )
    base = pd.DataFrame(
        {
            "chave": _normalize_url(df["inputUrl"]),
            "data": parse_publication_dates(df),
            "formato": formato.astype(str),
            "positivo": (df["sentiment_label"] == "positive").astype(int),
        }
    ).dropna(subset=["data"])
    if base.empty:
        return pd.DataFrame(columns=colunas)
    agregado = (
        base.groupby(["chave", "data", "formato"])["positivo"]
        .agg(positivos="sum", total="size")
        .reset_index()
    )
    return agregado[colunas]


def tendencia_nsm(
    df_comentarios: pd.DataFrame, chave_selecionada: str | None
) -> Tendencia:
    """Tendência da proporção de comentários positivos (ADR 0040, PROVISÓRIO).
    Governador selecionado: só a série dele (os outros perfis não entram, logo
    não a alteram). `None` ("Todos"): mediana das tendências de cada perfil,
    peso igual por perfil."""
    series = series_sentimento_por_dia(df_comentarios)

    def _de(perfil: pd.DataFrame) -> Tendencia:
        return tendencia_proporcao(
            perfil,
            coluna_positivos="positivos",
            coluna_total="total",
            coluna_formato="formato",
        )

    if chave_selecionada is None:
        return tendencia_conjunto([_de(g) for _, g in series.groupby("chave")])
    return _de(series[series["chave"] == chave_selecionada])


def _pct_sinal(valor: float) -> str:
    """Fração -> "+12,3%" / "−8,0%" (sinal sempre em texto)."""
    sinal = "+" if valor >= 0 else "−"
    return f"{sinal}{abs(valor) * 100:.1f}%".replace(".", ",")


def _texto_magnitude(t: Tendencia) -> str:
    return (
        f"{_pct_sinal(t.variacao)} (IC 95%: {_pct_sinal(t.ic_inferior)} a "
        f"{_pct_sinal(t.ic_superior)})"
    )


def html_tendencia(t: Tendencia | None) -> str:
    """Tendência sob o valor do cartão: seta + estado + magnitude e incerteza.
    "Estável" diz "sem evidência suficiente de mudança" (não "nada mudou");
    "Dados insuficientes" não tem seta nem número. Vazio sem tendência."""
    if t is None:
        return ""
    if t.estado == SUBINDO:
        tom, texto = "verde", f"▲ Subindo {_texto_magnitude(t)}"
    elif t.estado == CAINDO:
        tom, texto = "verm", f"▼ Caindo {_texto_magnitude(t)}"
    elif t.estado == ESTAVEL:
        tom = "neutro"
        texto = (
            "Estável · sem evidência suficiente de mudança "
            f"(estimativa {_texto_magnitude(t)})"
        )
    else:
        tom, texto = "neutro", INSUFICIENTE
    return f'<div class="n-tend {tom}">{texto}</div>'


def legenda_tendencia(t: Tendencia | None) -> str:
    """Legenda da Tendência, distinta da de SUBIU/CAIU (posição no ranking)."""
    if t is None:
        return ""
    base = (
        "Tendência no cartão de engajamento qualificado: variação estimada da "
        "proporção de comentários positivos ao longo do período coletado, sobre "
        "a série bruta por data (não o índice de 0–100), com o formato "
        "(reel/post) como controle e intervalo de confiança de 95%. "
        "Estável significa sem evidência suficiente de mudança, não que nada "
        "mudou. Tendência provisória: método e limiares ainda sem validação "
        "com dado real (ADR 0040, aguarda #284); a data usada é a do comentário. "
    )
    if t.n_perfis is not None:
        base += (
            "Em Todos: mediana das tendências dos perfis, cada um com o mesmo "
            f"peso (n = {t.n_perfis})."
        )
    return base


# Tokens de cor de dado (claro, escuro): azul/verde/vermelho reaproveitados
# dos tokens validados com a skill `dataviz` no Funil (superficies #fcfcfb /
# #1a1a19). Etiquetas e valores sempre tem texto, nunca so cor.
_AZUL = ("#2a78d6", "#5a9df0")
_VERDE = ("#008300", "#3fae3f")
_VERMELHO = ("#a32d2d", "#e66767")
_NEUTRO = ("#52525b", "#a1a1aa")


def _vars_cor(i: int) -> str:
    return (
        f"--n-azul:{_AZUL[i]};--n-verde:{_VERDE[i]};--n-verm:{_VERMELHO[i]};"
        f"--n-neutro:{_NEUTRO[i]};"
    )


_CSS_NSM = (
    "<style>"
    f".nsm-viz {{ {_vars_cor(0)} --n-trilho: rgba(128,128,128,.18); }}"
    "@media (prefers-color-scheme: dark) {"
    f' :root:where(:not([data-theme="light"])) .nsm-viz {{ {_vars_cor(1)} }} }}'
    f':root[data-theme="dark"] .nsm-viz {{ {_vars_cor(1)} }}'
    """
.nsm-viz .n-cards { display: flex; gap: 12px; flex-wrap: wrap; margin: 8px 0 18px; }
.nsm-viz .n-card { flex: 1 1 200px; border: 1px solid var(--n-trilho); border-radius: 10px;
  padding: 12px 16px; }
.nsm-viz .n-card.verde { border-left: 4px solid var(--n-verde); }
.nsm-viz .n-card.verm { border-left: 4px solid var(--n-verm); }
.nsm-viz .n-card-t { font-size: 12px; opacity: .75; }
.nsm-viz .n-card-v { font-size: 26px; font-weight: 500; }
.nsm-viz .n-card.verde .n-card-v { color: var(--n-verde); }
.nsm-viz .n-card.verm .n-card-v { color: var(--n-verm); }
.nsm-viz .n-card-s { font-size: 13px; opacity: .85; }
.nsm-viz .n-linha { display: flex; align-items: center; gap: 8px; margin: 4px 0;
  font-size: 13px; padding: 2px 6px; border-radius: 6px; }
.nsm-viz .n-linha.sel { outline: 2px solid currentColor; font-weight: 600; }
.nsm-viz .n-scroll { max-height: 320px; overflow-y: auto; padding-right: 4px; }
.nsm-viz .n-tend { font-size: 13px; font-weight: 600; }
.nsm-viz .n-tend.verde { color: var(--n-verde); }
.nsm-viz .n-tend.verm { color: var(--n-verm); }
.nsm-viz .n-tend.neutro { color: var(--n-neutro); }
.nsm-viz .n-pos { width: 28px; text-align: right; opacity: .7; }
.nsm-viz .n-nome { width: 150px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }
.nsm-viz .n-trilho { flex: 1; background: var(--n-trilho); border-radius: 4px; height: 16px; }
.nsm-viz .n-barra { height: 16px; border-radius: 4px; }
.nsm-viz .n-barra.azul { background: var(--n-azul); }
.nsm-viz .n-barra.verde { background: var(--n-verde); }
.nsm-viz .n-val { width: 64px; text-align: right; }
.nsm-viz .n-et { font-size: 11px; border-radius: 6px; padding: 0 6px; min-width: 56px;
  text-align: center; border: 1px solid currentColor; }
.nsm-viz .n-et.subiu { color: var(--n-verde); }
.nsm-viz .n-et.caiu { color: var(--n-verm); }
.nsm-viz .n-sel-tag { font-size: 11px; opacity: .8; }
</style>"""
)


def _html_cartao(
    titulo: str, valor: str, sub: str, tom: str | None, tendencia: str = ""
) -> str:
    return (
        f'<div class="n-card {tom or ""}"><div class="n-card-t">{html.escape(titulo)}'
        f'</div><div class="n-card-v">{html.escape(valor)}</div>{tendencia}'
        f'<div class="n-card-s">{html.escape(sub)}</div></div>'
    )


def _html_ranking(linhas: list[dict], cor: str, fmt) -> str:
    if not linhas:
        return "<div>Sem dados.</div>"
    maximo = max(item["valor"] for item in linhas) or 1.0
    partes = []
    for item in linhas:
        largura = max(2.0, item["valor"] / maximo * 100.0) if item["valor"] > 0 else 0.0
        et = ""
        if item["etiqueta"]:
            seta = "▲" if item["etiqueta"] == ETIQUETA_SUBIU else "▼"
            et = (
                f'<span class="n-et {item["etiqueta"].lower()}">'
                f"{seta} {item['etiqueta']}</span>"
            )
        tag = (
            ' <span class="n-sel-tag">(selecionado)</span>'
            if item["selecionado"]
            else ""
        )
        classes = "n-linha" + (" sel" if item["selecionado"] else "")
        nome = html.escape(item["nome"])
        partes.append(
            f'<div class="{classes}"><span class="n-pos">{item["posicao"]}º</span>'
            f'<span class="n-nome" title="{nome}">{nome}{tag}</span>'
            f'<span class="n-trilho"><div class="n-barra {cor}" '
            f'style="width:{largura:.1f}%"></div></span>'
            f'<span class="n-val">{fmt(item["valor"])}</span>{et}</div>'
        )
    return f'<div class="n-scroll">{"".join(partes)}</div>'


def _fmt_nsm_0_100(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return _PLACEHOLDER_SEM_GOVERNADOR
    return f"{valor:.1f}"


def _render_contraste(governor_url: str, is_todos: bool) -> None:
    comentarios = data.comments_only(data.load_sentiment())
    tabela = montar_tabela_contraste(
        data.load_nsm(), comentarios, data.load_governors_metadata()
    )
    chave = None if is_todos else _normalize_url(pd.Series([governor_url])).iloc[0]

    st.markdown("### North Star Metric — Engajamento Positivo Qualificado")
    st.markdown(
        "A métrica-norte mede valor entregue (aprovação real), não esforço. "
        "O contraste abaixo mostra que alto engajamento não é alta aprovação."
    )
    if tabela.empty:
        st.info("Ainda não há dados de engajamento qualificado.")
        return

    valor = valor_cartao_nsm(tabela, chave)
    melhor = extremo_com_amostra(tabela, "pct_pos")
    pior = extremo_com_amostra(tabela, "pct_neg")
    tendencia = tendencia_nsm(comentarios, chave)
    cartoes = [
        _html_cartao(
            "Engajamento qualificado" + (" (média dos perfis)" if is_todos else ""),
            _fmt_nsm_0_100(valor),
            "índice de 0 a 100",
            "verde",
            tendencia=html_tendencia(tendencia),
        ),
        _html_cartao(
            "Melhor aprovação",
            _fmt_pct(melhor[1]) if melhor else _PLACEHOLDER_SEM_GOVERNADOR,
            f"{melhor[0]} · {melhor[2]} comentários"
            if melhor
            else f"nenhum perfil com {MIN_COMENTARIOS_CARTAO}+ comentários",
            None,
        ),
        _html_cartao(
            "Maior rejeição",
            _fmt_pct(pior[1]) if pior else _PLACEHOLDER_SEM_GOVERNADOR,
            f"{pior[0]} · {pior[2]} comentários"
            if pior
            else f"nenhum perfil com {MIN_COMENTARIOS_CARTAO}+ comentários",
            "verm",
        ),
    ]
    esq = linhas_ranking(tabela, "bruto", chave)
    dir_ = linhas_ranking(tabela, "nsm", chave, com_etiqueta=True)
    st.markdown(
        f'{_CSS_NSM}<div class="nsm-viz"><div class="n-cards">{"".join(cartoes)}</div>'
        '<div style="display:flex;gap:24px;flex-wrap:wrap;">'
        '<div style="flex:1 1 360px;"><strong>Por engajamento bruto</strong>'
        f"{_html_ranking(esq, 'azul', _fmt_int_br)}</div>"
        '<div style="flex:1 1 360px;"><strong>Por engajamento qualificado</strong>'
        f"{_html_ranking(dir_, 'verde', _fmt_nsm_0_100)}</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Engajamento bruto = total de curtidas e comentários por perfil. "
        "SUBIU/CAIU compara a posição no ranking qualificado com a do bruto. "
        f"Melhor aprovação e Maior rejeição só consideram perfis com pelo menos {MIN_COMENTARIOS_CARTAO} comentários. "
        + legenda_tendencia(tendencia)
    )


# ---------------------------------------------------------------------------
# render()
# ---------------------------------------------------------------------------


def render(governor_url: str) -> None:
    """Renderiza a sub-aba NSM para `governor_url` (URL real ou
    `TODOS_OS_GOVERNADORES`)."""
    _render_contraste(governor_url, governor_url == TODOS_OS_GOVERNADORES)
