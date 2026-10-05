"""Sub-aba Scorecard do Resumo (ADR 0030 / ADR 0031, issue #188, spec #182).

Ranking dos governadores por escore composto, lendo a tabela Gold
`governor_scorecard` -- o dashboard só lê, nada é recalculado aqui. Cada
dimensão (Alcance, Ativação, Qualidade, Profundidade, Consistência) é uma
barra horizontal com o escore normalizado 0-100 e o valor numérico.

Funções puras (`montar_linhas`, `fmt_valor`, `legenda_pesos`, `html_tabela`)
concentram a lógica testável; `render` só orquestra o Streamlit.
"""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from dashboard.core import data
from dashboard.screens.resumo_comum import (
    _PLACEHOLDER_SEM_GOVERNADOR,
    TODOS_OS_GOVERNADORES,
    _normalize_url,
)

TITULO = "Scorecard Composto por Perfil"
TEXTO_INTRO = (
    "Índice composto: pontua cada governador em cinco dimensões do funil, "
    "normalizadas 0–100 e agregadas por soma ponderada. O ranking é "
    "decomponível: mostra a posição e em quais dimensões cada perfil ganha "
    "ou perde."
)
SELO_CONFIABILIDADE = (
    "Leitura com cautela: a Consistência mede a tendência do engajamento dos "
    "posts por mês de publicação, não crescimento de audiência. O Alcance é "
    "medido em reproduções (plays) dos reels."
)
AVISO_SEM_TABELA = (
    "O Scorecard ainda não foi gerado -- rode o estágio do escore composto "
    "(`uv run python scripts/run_governor_scorecard.py`) ou a pipeline de "
    "modelagem para popular esta sub-aba."
)

# (chave, rótulo) na ordem de exibição.
DIMENSOES: list[tuple[str, str]] = [
    ("alcance", "Alcance"),
    ("ativacao", "Ativação"),
    ("qualidade", "Qualidade"),
    ("profundidade", "Profundidade"),
    ("consistencia", "Consistência"),
]

# Paleta categórica /dataviz (validada: tokens claro, escuro) -- azul, laranja,
# verde, roxo, âmbar. O âmbar/verde ficam abaixo de 3:1 no claro; o valor
# numérico sempre visível ao lado da barra é o alívio exigido.
CORES_DIMENSAO: dict[str, tuple[str, str]] = {
    "alcance": ("#2a78d6", "#3987e5"),
    "ativacao": ("#eb6834", "#d95926"),
    "qualidade": ("#1baf7a", "#199e70"),
    "profundidade": ("#4a3aa7", "#9085e9"),
    "consistencia": ("#eda100", "#c98500"),
}
_COR_DESTAQUE = ("rgba(42,120,214,.14)", "rgba(57,135,229,.22)")

_TEXTO_PENDENTE = "pendente"
_TEXTO_SEM_DADO = "sem dado"
_PESO_5 = "0,20"


# ---------------------------------------------------------------------------
# Funções puras
# ---------------------------------------------------------------------------


def fmt_valor(valor: float | None) -> str:
    """Escore 0-100 com 1 casa e vírgula decimal (pt-BR); `—` se ausente."""
    if valor is None or pd.isna(valor):
        return _PLACEHOLDER_SEM_GOVERNADOR
    return f"{valor:.1f}".replace(".", ",")


def _fmt_peso(n_dimensoes: int) -> str:
    return f"{1 / n_dimensoes:.2f}".replace(".", ",")


def legenda_pesos(df: pd.DataFrame) -> str:
    """Legenda de pesos; menciona os pesos renormalizados quando algum perfil
    com escore usa menos de cinco dimensões (Consistência pendente)."""
    texto = f"Pesos iguais ({_PESO_5} cada). Barras = escore normalizado da dimensão."
    if df.empty or "n_dimensoes" not in df.columns or "escore" not in df.columns:
        return texto
    com_escore = df[df["escore"].notna()]
    reduzidos = com_escore[com_escore["n_dimensoes"] < len(DIMENSOES)]
    if reduzidos.empty:
        return texto
    pesos = sorted({_fmt_peso(int(n)) for n in reduzidos["n_dimensoes"]})
    return (
        f"Pesos iguais ({_PESO_5} cada). Com uma dimensão pendente, os pesos "
        f"são renormalizados ({' / '.join(pesos)} cada). "
        "Barras = escore normalizado da dimensão."
    )


def _celula(linha: pd.Series, chave: str) -> dict:
    valor = linha.get(f"{chave}_norm")
    if valor is None or pd.isna(valor):
        pendente = chave == "consistencia" and bool(
            linha.get("consistencia_pendente", True)
        )
        return {
            "chave": chave,
            "pendente": pendente,
            "texto": _TEXTO_PENDENTE if pendente else _TEXTO_SEM_DADO,
            "largura": None,
        }
    largura = min(100.0, max(0.0, float(valor)))
    return {
        "chave": chave,
        "pendente": False,
        "texto": fmt_valor(valor),
        "largura": largura,
    }


def _nota(linha: pd.Series, tem_escore: bool) -> str:
    n = int(linha["n_dimensoes"]) if pd.notna(linha.get("n_dimensoes")) else 0
    if not tem_escore:
        return f"Sem escore: dados insuficientes ({n} de {len(DIMENSOES)} dimensões)."
    if n < len(DIMENSOES):
        return (
            f"Escore calculado com {n} dimensões (pesos {_fmt_peso(n)} cada); "
            "Consistência pendente."
        )
    return ""


def montar_linhas(
    df: pd.DataFrame,
    governor_url: str | None,
    df_metadata: pd.DataFrame | None = None,
) -> list[dict]:
    """Linhas da tabela de ranking, na ordem gravada (`ranking` crescente;
    perfis sem posição por último, por nome). Lista vazia se `df` não tiver as
    colunas esperadas."""
    if df.empty or not {"inputUrl", "escore", "ranking"} <= set(df.columns):
        return []

    nomes: dict[str, str] = {}
    if (
        df_metadata is not None
        and not df_metadata.empty
        and {"inputUrl", "nome"} <= set(df_metadata.columns)
    ):
        chaves = _normalize_url(df_metadata["inputUrl"])
        nomes = {
            k: n
            for k, n in zip(chaves, df_metadata["nome"], strict=True)
            if isinstance(n, str) and n.strip()
        }

    selecionado = (
        None
        if governor_url in (None, TODOS_OS_GOVERNADORES)
        else _normalize_url(pd.Series([governor_url])).iloc[0]
    )

    df = df.copy()
    df["_chave"] = _normalize_url(df["inputUrl"])
    df["_nome"] = [
        nomes.get(chave) or (user if isinstance(user, str) and user else url)
        for chave, user, url in zip(
            df["_chave"],
            df["username"] if "username" in df.columns else [None] * len(df),
            df["inputUrl"],
            strict=True,
        )
    ]
    df = df.sort_values(
        ["ranking", "_nome"], na_position="last", kind="stable"
    ).reset_index(drop=True)

    linhas = []
    for _, linha in df.iterrows():
        tem_escore = pd.notna(linha["escore"])
        tem_posicao = pd.notna(linha["ranking"])
        linhas.append(
            {
                "posicao": str(int(linha["ranking"]))
                if tem_posicao
                else _PLACEHOLDER_SEM_GOVERNADOR,
                "nome": linha["_nome"],
                "dimensoes": [_celula(linha, chave) for chave, _ in DIMENSOES],
                "escore_texto": fmt_valor(linha["escore"]),
                "destacado": selecionado is not None
                and linha["_chave"] == selecionado,
                "nota": _nota(linha, bool(tem_escore)),
            }
        )
    return linhas


# ---------------------------------------------------------------------------
# HTML / CSS
# ---------------------------------------------------------------------------


def _css_vars(indice: int) -> str:
    vars_ = "".join(f"--sc-{k}:{v[indice]};" for k, v in CORES_DIMENSAO.items())
    return vars_ + f"--sc-hl:{_COR_DESTAQUE[indice]};"


_CSS = (
    "<style>"
    f".sc-viz {{ {_css_vars(0)} --sc-track: rgba(128,128,128,.18); }}"
    "@media (prefers-color-scheme: dark) {"
    f' :root:where(:not([data-theme="light"])) .sc-viz {{ {_css_vars(1)} }} }}'
    f':root[data-theme="dark"] .sc-viz {{ {_css_vars(1)} }}'
    """
.sc-viz { overflow-x: auto; }
.sc-viz table { width: 100%; border-collapse: collapse; font-size: 13px; }
.sc-viz th { text-align: left; font-weight: 500; opacity: .7; padding: 6px 8px;
  border-bottom: 1px solid var(--sc-track); white-space: nowrap; }
.sc-viz td { padding: 6px 8px; border-bottom: 1px solid var(--sc-track);
  vertical-align: middle; }
.sc-viz tr.sc-hl td { background: var(--sc-hl); }
.sc-viz .sc-pos { opacity: .7; width: 32px; }
.sc-viz .sc-nome { min-width: 140px; }
.sc-viz .sc-nota { display: block; font-size: 11px; opacity: .7; margin-top: 2px; }
.sc-viz .sc-cel { display: flex; align-items: center; gap: 6px; min-width: 110px; }
.sc-viz .sc-track { flex: 1; background: var(--sc-track); border-radius: 4px; height: 8px; }
.sc-viz .sc-bar { height: 8px; border-radius: 4px; }
.sc-viz .sc-val { width: 34px; text-align: right; font-variant-numeric: tabular-nums; }
.sc-viz .sc-pend { opacity: .6; font-style: italic; }
.sc-viz .sc-escore { text-align: right; font-weight: 600; font-size: 15px;
  font-variant-numeric: tabular-nums; }
.sc-viz th.sc-escore { font-size: 13px; }
</style>"""
)


def _html_celula(cel: dict) -> str:
    if cel["largura"] is None:
        return f'<td><span class="sc-pend">{html.escape(cel["texto"])}</span></td>'
    return (
        '<td><div class="sc-cel"><div class="sc-track">'
        f'<div class="sc-bar" style="width:{cel["largura"]:.1f}%;'
        f'background:var(--sc-{cel["chave"]});"></div></div>'
        f'<span class="sc-val">{html.escape(cel["texto"])}</span></div></td>'
    )


def html_tabela(linhas: list[dict]) -> str:
    cab = "".join(f"<th>{rotulo}</th>" for _, rotulo in DIMENSOES)
    corpo = []
    for linha in linhas:
        nota = (
            f'<span class="sc-nota">{html.escape(linha["nota"])}</span>'
            if linha["nota"]
            else ""
        )
        classe = ' class="sc-hl"' if linha["destacado"] else ""
        celulas = "".join(_html_celula(c) for c in linha["dimensoes"])
        corpo.append(
            f"<tr{classe}><td class=\"sc-pos\">{html.escape(linha['posicao'])}</td>"
            f'<td class="sc-nome">{html.escape(linha["nome"])}{nota}</td>'
            f"{celulas}"
            f'<td class="sc-escore">{html.escape(linha["escore_texto"])}</td></tr>'
        )
    return (
        f'<div class="sc-viz">{_CSS}<table><thead><tr><th>#</th><th>Governador</th>'
        f'{cab}<th class="sc-escore">Escore</th></tr></thead>'
        f"<tbody>{''.join(corpo)}</tbody></table></div>"
    )


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def render(governor_url: str) -> None:
    st.subheader(TITULO)
    st.write(TEXTO_INTRO)

    df = data.load_governor_scorecard()
    linhas = montar_linhas(df, governor_url, data.load_governors_metadata())
    if not linhas:
        st.info(AVISO_SEM_TABELA)
        return

    st.caption(legenda_pesos(df))
    st.warning(SELO_CONFIABILIDADE, icon="⚠️")
    st.markdown(html_tabela(linhas), unsafe_allow_html=True)
