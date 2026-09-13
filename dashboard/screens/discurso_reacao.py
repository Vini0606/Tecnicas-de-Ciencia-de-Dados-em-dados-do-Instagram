"""Tela 5 -- "Discurso x reação" (ADR 0021 / issue #116, última da reformulação).

Responde "estou falando do que o público quer?" cruzando DOIS espaços de
tópicos de DOIS modelos BERTopic distintos e não relacionados entre si:

- Discurso (o que a assessoria FALA): `load_discourse_topics()` --
  `governor_discourse_topics`, BERTopic sobre legenda+transcrição (issue #89).
- Reação (o que o PÚBLICO reage): `comments_only(load_sentiment())` --
  `governor_sentiment` filtrado a `fonte == 'comentario'`, BERTopic sobre
  comentário (issue #52/#61).

As duas tabelas usam o MESMO NOME de coluna para o rótulo do tópico (`Name`,
confirmado em `src/schemas_delta.py` -- `GOLD_DISCOURSE_TOPICS_SCHEMA` e
`GOLD_SENTIMENT_SCHEMA`), mas são dois vocabulários de tópico TOTALMENTE
diferentes (modelos treinados sobre corpora diferentes, com `Topic`/`Name`
próprios). Comparar os dois lados por `Topic` (ou até por `Name` cru) seria
uma coincidência sem sentido -- ver issue #116, user story 3. Por isso as
duas distribuições são projetadas numa TAXONOMIA COMUM curada (`TAXONOMIA`
abaixo) antes de qualquer comparação; o cruzamento nunca acontece por ID.

Mesma estrutura fixa das Telas 1/2/3/4 (ver `dashboard/screens/resumo.py`,
ADR 0021 -- Princípio de design): cabeçalho (governador) -> `stage_label` ->
frase de decisão -> duas colunas de barra (discurso vs. reação) -> duas
frases automáticas de leitura -> rodapé. Toda a lógica de decisão vive em
funções puras nomeadas abaixo, testadas em
`tests/test_dashboard_screens_discurso_reacao.py` -- `render()` só orquestra
I/O do Streamlit sobre o resultado dessas funções.

-------------------------------------------------------------------------
CURADORIA DA TAXONOMIA -- ver PR da issue #116 para a íntegra do
levantamento. Resumo do método:

Os rótulos brutos abaixo (`TAXONOMIA`) foram observados diretamente num
snapshot real de Gold emprestado de um worktree irmão desta sessão
(`data_backup_20260912_062611/gold/{governor_discourse_topics,
governor_sentiment}`, mesmo procedimento já usado pelo implementador da
Tela 4/issue #115) -- carregados via `DeltaRepository.load_discourse_topics()`
/`load_comments()` reais, NUNCA inventados. `governor_discourse_topics` tinha
302 linhas / 17 tópicos distintos (todos os 27 governadores combinados);
`governor_sentiment` (só `fonte == 'comentario'`) tinha 1608 linhas / 44
tópicos distintos.

Achado central (documentado à exaustão no PR, resumido aqui): os rótulos
observados nos dois modelos NÃO se organizam naturalmente em torno de temas
de política pública (saúde/segurança/educação) como a lista de exemplo da
ADR sugeria -- a lista abaixo foi ajustada ao que os dados realmente mostram
(issue #116, Implementation Decisions: "ajustar a lista conforme os rótulos
reais observados"), não forçada a um vocabulário de política pública que os
27 perfis não produziram nesta amostra:

- Discurso (legenda/transcrição): dominado por slogans de campanha/marca
  política (hashtags, nomes de candidato, números de urna -- 8/17 tópicos,
  ~31% das linhas) e por um ÚNICO tópico degenerado sem palavra nenhuma
  (`"0____"`, 110/302 linhas = 36% de TODO o discurso -- legendas curtas
  demais para o BERTopic extrair um termo distintivo). "Obras" (2 tópicos,
  ~9%) e "economia" (crescimento/prosperidade, 3 tópicos, ~8%) aparecem, mas
  pequenos. Nenhum tópico de discurso fala claramente de saúde, segurança ou
  educação nesta amostra.
- Reação (comentário): dominada por reação emotiva genérica em emoji
  (aplausos, corações, teclas numéricas -- 26/44 tópicos, 54% das linhas) e
  por menções de campanha/candidato (14/44 tópicos, 22%). Só 1 tópico de
  crítica (arruinou/descaso/estrago/ridículo, 7%) e 1 de educação
  ("educação é nossa força", 3%) têm conteúdo temático claro.

Por isso a lista de temas de alto nível abaixo reflete o que os dois modelos
realmente produzem hoje (campanha, obras, economia, educação, fé/agradeci-
mento, crítica, reação emotiva), não a lista ilustrativa
saúde/segurança/economia/obras/educação do enunciado da issue -- ver PR para
a tabela completa rótulo-a-rótulo e a taxa de cobertura exata (rótulos não
mapeados caem em OUTROS, nunca lançam exceção -- ver `_projetar_tema`).

Convenção adotada para `Topic == -1` (bucket de ruído do próprio BERTopic,
não um tema de negócio) em AMBOS os modelos: cai sempre em OUTROS, nunca
recebe um tema curado -- mesma convenção já usada por `comparar.py`/Tela 4
para `cluster_label == -1` ("nunca inventar um nome de negócio para o que o
próprio algoritmo já sinalizou como não-agrupável").
-------------------------------------------------------------------------
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.core import data
from dashboard.core.components import decision_band, footnote, stage_label
from dashboard.core.theme import COLORS

_PLACEHOLDER_SEM_GOVERNADOR = "—"
_STAGE = "Convert (Contribuir)"

_TEMA_OUTROS = "outros"

# Ordem de exibição dos temas curados nas duas colunas de barra (sempre a
# MESMA ordem nos dois lados, para comparação direta) -- "outros" é sempre
# acrescentado por último por `_ordem_temas_exibicao`, nunca hardcoded aqui,
# para nunca esconder tópico não mapeado (issue #116: "cair em outros
# graciosamente", não silenciosamente sumir do gráfico).
TEMAS_ORDEM: list[str] = [
    "obras",
    "economia",
    "educação",
    "campanha e mobilização política",
    "fé e agradecimento",
    "crítica e insatisfação",
    "reação emotiva (emojis)",
]

# ---------------------------------------------------------------------------
# TAXONOMIA -- mapa curado de rótulo bruto (`Name`, de QUALQUER um dos dois
# modelos BERTopic) -> tema de alto nível. Ver docstring do módulo para a
# metodologia e o PR da issue #116 para a tabela completa rótulo-a-rótulo
# (frequência, modelo de origem). `Topic == -1` de propósito NUNCA aparece
# aqui (ver docstring, "Convenção para Topic == -1") -- cai em OUTROS via
# `_projetar_tema`.
# ---------------------------------------------------------------------------
TAXONOMIA: dict[str, list[str]] = {
    "obras": [
        # Discurso (governor_discourse_topics)
        "3_asfalto_entregamos_canutama_farra",
        "7_acelerada_caravana_joãopratodaobra_acelerado",
    ],
    "economia": [
        # Discurso -- slogans de crescimento/prosperidade
        "9_sergipecrescecomvoce_sergipanos_sergipe_aracajuanos",
        "12_sergipecrescecomvoce_iremos_continuarmos_seguimos",
        "13_alcançamos_conquistamos_2026_prospere",
    ],
    "educação": [
        # Reação (governor_sentiment, fonte=comentario) -- único tópico com
        # menção explícita a educação em qualquer um dos dois modelos.
        "5_educaçãoénossaforça_15_vamos_juntos",
    ],
    "campanha e mobilização política": [
        # Discurso -- hashtags de campanha, nomes de candidato, carreata/mobilização
        "2_juventudecomsandroalex_eduardopimentel_sandroalex_time55",
        "4_portodooamapá_aforçadonovotempo_clécioluís_amapá",
        "5_timedopovo_carreata_piauiense_carinho",
        "6_mudamaisbahia_jero13_rui133_bahia",
        "8_0001_594_osenadordetodos_democrata",
        "10_mobiliza_fizemos_cearense_0001",
        "11_raquellyraoficial_vocês_teodora_agreste",
        "15_senadordetodosnós_queremos_tôcomriedel_comprometido",
        # Reação -- menção a candidato/político real, número de urna, linguagem eleitoral
        "3_foguete_vumbora_fogo_fonteles",
        "10_mãos_aplaudindo_jorginhomello__",
        "19_governador_senador_estadual_tocantins",
        "23_mãos_aplaudindo_mãos_juntas_juntos_riedel",
        "25_coração_roxo_rosto_sorridente_com_olhos_de_coração_tamos_raquel",
        "27_coração_vermelho_coração_azul_foguete_chicaodopara",
        "30_tecla_5_tecla_1_sandroalex_rafaelgrecaoficial",
        "31_mãos_aplaudindo_mãos_juntas_avante_vitoria",
        "34_13___",
        "35_reeleito_reeleger_petista_votar",
        "36_governadora_mãos_de_coração_pele_clara_coração_roxo_querida",
        "38_mãos_aplaudindo_marca_de_seleção_branca_presidente_",
        "41_55456_coração_azul_coração_roxo_foguete",
        "42_coração_roxo_tecla_5_bandeira_brasil_túlio",
    ],
    "fé e agradecimento": [
        # Discurso
        "14_bênçãos_parabéns_bênção_abençoe",
        # Reação
        "32_abençoe_amémmmmm_abençoando_bençãos",
    ],
    "crítica e insatisfação": [
        # Reação -- único tópico de crítica clara em qualquer um dos dois modelos
        "0_arruinou_descaso_estrago_ridículo",
    ],
    "reação emotiva (emojis)": [
        # Reação -- tópicos dominados por emoji de aplauso/coração/tecla sem
        # nome de candidato nem palavra temática (ver docstring do módulo).
        "1_mãos_aplaudindo_polegar_para_cima_literalmente_desenhando",
        "2_mãos_aplaudindo_mãos_juntas_bandeira_brasil_concordo",
        "4_mãos_aplaudindo_tempos_bons_trabalhar",
        "6_tecla_3_tecla_1_tecla_4_tecla_0",
        "7_mãos_aplaudindo_mãos_aplaudindo_pele_clara_mãos_para_cima_rosto_sorridente_com_olhos_de_coração",
        "8_coração_azul_coração_vermelho_chicão_azul",
        (
            "9_mãos_aplaudindo_pele_morena_clara_mãos_aplaudindo_pele_morena_escura_"
            "mãos_aplaudindo_pele_morena_mãos_aplaudindo_pele_clara"
        ),
        "11_tecla_4_marca_de_seleção_branca_tecla_0_coração_amarelo",
        "12_tecla_5_marca_de_seleção_branca_tecla_1_tecla_4",
        "13_rosto_chorando_de_rir_rosto_chorando_rosto_triste_mas_aliviado_rosto_furioso",
        "14_parabéns_mãos_aplaudindo_mãos_para_cima_admiro",
        "15_mãos_aplaudindo_mãos_para_cima_mãos_de_coração_aperto_de_mãos",
        "16_tecla_3_tecla_1_coração_vermelho_tecla_0",
        "17_tecla_5_coração_azul_foguete_tecla_1",
        "18_tecla_5_tecla_1_foguete_indicador_apontando_para_cima",
        "20_tecla_4_foguete_tecla_7_tecla_1",
        (
            "21_dorso_da_mão_com_indicador_apontando_para_a_direita_pele_morena_"
            "bandeira_brasil_tecla_7_coração_vermelho"
        ),
        "22_mãos_aplaudindo_mãos_aplaudindo_pele_clara_tecla_5_tecla_3",
        (
            "24_rosto_sorridente_com_olhos_de_coração_rosto_sorridente_com_óculos_"
            "escuros_rosto_com_olhar_maravilhado_rosto_com_boca_aberta"
        ),
        "26_mãos_para_cima_polegar_para_cima_mãos_para_cima_pele_clara_mãos_aplaudindo",
        "28_tecla_5_coração_azul_tecla_1_coração_verde",
        "29_coração_vermelho_coração_laranja_coração_verde_rosto_sorridente_com_olhos_de_coração",
        (
            "33_rosto_sorridente_com_olhos_de_coração_mãos_aplaudindo_rosto_segurando_"
            "as_lágrimas_rosto_chorando_de_rir"
        ),
        "37_coração_roxo_quadrado_roxo_coração_amarelo_coração_decorativo",
        "39_coração_vermelho_coração_amarelo_coração_em_chamas_mãos_para_cima",
        "40_mãos_aplaudindo_coração_azul_coração_vermelho_tecla_5",
    ],
}


def _construir_mapa_rotulo_para_tema(taxonomia: dict[str, list[str]]) -> dict[str, str]:
    """Inverte `TAXONOMIA` (tema -> [rótulos]) para `rótulo -> tema`, a
    direção que `_projetar_tema` precisa para lookup O(1). Função separada
    (em vez de um dict literal invertido à mão) para que `TAXONOMIA`
    continue na forma pedida pela issue (`{tema: [rótulos]}`), mais fácil de
    revisar/curar do que o inverso."""
    mapa: dict[str, str] = {}
    for tema, rotulos in taxonomia.items():
        for rotulo in rotulos:
            mapa[rotulo] = tema
    return mapa


_MAPA_ROTULO_TEMA = _construir_mapa_rotulo_para_tema(TAXONOMIA)


def _projetar_tema(rotulo_bruto: object) -> str:
    """Projeta um rótulo bruto de tópico (`Name`, de QUALQUER um dos dois
    modelos BERTopic -- discurso ou comentário) no tema de alto nível
    correspondente, via `TAXONOMIA`. `_TEMA_OUTROS` (nunca uma exceção) para
    qualquer rótulo ausente do mapa -- `None`/`NaN` (tópico não atribuído)
    ou um rótulo novo que a curadoria ainda não viu (ex.: BERTopic re-treinado
    com um corpus diferente) -- issue #116, Implementation Decisions:
    "Rótulos não mapeados devem cair em 'outros' de forma graciosa, nunca
    lançar exceção"."""
    if rotulo_bruto is None or (isinstance(rotulo_bruto, float) and pd.isna(rotulo_bruto)):
        return _TEMA_OUTROS
    return _MAPA_ROTULO_TEMA.get(str(rotulo_bruto), _TEMA_OUTROS)


def _ordem_temas_exibicao() -> list[str]:
    """`TEMAS_ORDEM` + `_TEMA_OUTROS` sempre por último -- mesma ordem nas
    duas colunas de barra, para que discurso e reação fiquem comparáveis
    tema a tema (issue #116, user story 2)."""
    return [*TEMAS_ORDEM, _TEMA_OUTROS]


# ---------------------------------------------------------------------------
# Distribuição percentual por tema (issue #116, Testing Decisions: função
# pura de projeção + distribuição, testada com DataFrame sintético).
# ---------------------------------------------------------------------------


def _distribuicao_percentual_por_tema(df: pd.DataFrame, coluna_rotulo: str = "Name") -> dict[str, float]:
    """1 valor por tema de `_ordem_temas_exibicao()` (0.0 se o tema não
    aparecer nesta tabela) -- proporção de linhas de `df` cujo `coluna_rotulo`
    projeta (via `_projetar_tema`) para aquele tema. Soma dos valores = 1.0
    quando `df` não está vazio (todo tema não-curado cai em OUTROS, nunca é
    descartado). `DataFrame` vazio ou sem `coluna_rotulo` -> todos os temas
    em 0.0 (nunca `ZeroDivisionError`/exceção)."""
    temas = _ordem_temas_exibicao()
    if df.empty or coluna_rotulo not in df.columns or len(df) == 0:
        return dict.fromkeys(temas, 0.0)

    total = len(df)
    contagem = df[coluna_rotulo].map(_projetar_tema).value_counts()
    return {tema: contagem.get(tema, 0) / total for tema in temas}


# ---------------------------------------------------------------------------
# Tabela de gap (reação% - discurso%) -- issue #116, Implementation
# Decisions / Testing Decisions: função pura, testada com dicts sintéticos.
# ---------------------------------------------------------------------------


def _montar_tabela_gap(
    dist_discurso: dict[str, float], dist_reacao: dict[str, float]
) -> pd.DataFrame:
    """1 linha por tema de `_ordem_temas_exibicao()`: `pct_discurso`,
    `pct_reacao`, `gap` (= `pct_reacao - pct_discurso`, positivo = público
    reage mais do que a assessoria fala sobre aquele tema). `_TEMA_OUTROS` é
    incluído na tabela (para o gráfico -- ver `_distribuicao_percentual_por_tema`)
    mas as funções de leitura automática abaixo (`_tema_produzir_mais`/
    `_tema_reduzir_reformular`/`_tema_decisao`) o ignoram explicitamente:
    recomendar "produza mais sobre outros" não tem ação concreta nenhuma."""
    temas = _ordem_temas_exibicao()
    linhas = [
        {
            "tema": tema,
            "pct_discurso": dist_discurso.get(tema, 0.0),
            "pct_reacao": dist_reacao.get(tema, 0.0),
            "gap": dist_reacao.get(tema, 0.0) - dist_discurso.get(tema, 0.0),
        }
        for tema in temas
    ]
    return pd.DataFrame(linhas)


def _temas_acionaveis(tabela_gap: pd.DataFrame) -> pd.DataFrame:
    """`tabela_gap` sem a linha `_TEMA_OUTROS` -- usado por toda função de
    leitura automática/decisão abaixo (nunca pelo gráfico, que mostra
    `_TEMA_OUTROS` normalmente para transparência de cobertura)."""
    return tabela_gap[tabela_gap["tema"] != _TEMA_OUTROS]


def _tema_produzir_mais(tabela_gap: pd.DataFrame) -> dict | None:
    """Tema com o maior gap POSITIVO (`pct_reacao - pct_discurso`) entre os
    temas acionáveis -- "produza mais sobre X" (issue #116, user story 4).
    `None` (nunca inventa um destaque) se não houver nenhum gap
    estritamente positivo."""
    candidatos = _temas_acionaveis(tabela_gap)
    candidatos = candidatos[candidatos["gap"] > 0]
    if candidatos.empty:
        return None
    linha = candidatos.loc[candidatos["gap"].idxmax()]
    return linha.to_dict()


def _tema_reduzir_reformular(tabela_gap: pd.DataFrame) -> dict | None:
    """Tema com o maior gap NEGATIVO (discurso acima da reação) entre os
    temas acionáveis -- "reduza/reformule Y" (issue #116, user story 4).
    `None` se não houver nenhum gap estritamente negativo."""
    candidatos = _temas_acionaveis(tabela_gap)
    candidatos = candidatos[candidatos["gap"] < 0]
    if candidatos.empty:
        return None
    linha = candidatos.loc[candidatos["gap"].idxmin()]
    return linha.to_dict()


def _tema_decisao(tema_produzir: dict | None, tema_reduzir: dict | None) -> dict | None:
    """Tema da faixa de decisão -- ENTRE `tema_produzir` (maior gap
    positivo) e `tema_reduzir` (maior gap negativo), o de maior `|gap|`
    (issue #116, Implementation Decisions: "o tema de maior |reação% -
    discurso%| entre os dois com sinais opostos"). `None` só quando nenhum
    dos dois existe (nenhum gap não-nulo entre os temas acionáveis)."""
    candidatos = [t for t in (tema_produzir, tema_reduzir) if t is not None]
    if not candidatos:
        return None
    return max(candidatos, key=lambda t: abs(t["gap"]))


def _fmt_pct(valor: float) -> str:
    return f"{valor * 100:.0f}%"


def _frase_produzir_mais(tema: dict | None) -> str:
    if tema is None:
        return "Nenhum tema com reação acima do discurso no momento."
    return (
        f'O público reage mais a "{tema["tema"]}" ({_fmt_pct(tema["pct_reacao"])} dos '
        f'comentários) do que a assessoria fala sobre isso ({_fmt_pct(tema["pct_discurso"])} '
        "do discurso) -- produza mais sobre esse tema."
    )


def _frase_reduzir_reformular(tema: dict | None) -> str:
    if tema is None:
        return "Nenhum tema com discurso acima da reação no momento."
    return (
        f'A assessoria fala bastante de "{tema["tema"]}" ({_fmt_pct(tema["pct_discurso"])} do '
        f'discurso), mas o público reage pouco a isso ({_fmt_pct(tema["pct_reacao"])} dos '
        "comentários) -- reduza ou reformule esse tema."
    )


def _frase_decisao(tema_decisao: dict | None) -> str:
    if tema_decisao is None:
        return (
            "Sem gap identificável entre discurso e reação no momento -- dado "
            "insuficiente para comparar os dois lados."
        )
    if tema_decisao["gap"] > 0:
        return (
            f'Você fala pouco de "{tema_decisao["tema"]}", mas o público reage mais a isso '
            f'({_fmt_pct(tema_decisao["pct_reacao"])} dos comentários vs. '
            f'{_fmt_pct(tema_decisao["pct_discurso"])} do discurso).'
        )
    return (
        f'Você fala bastante de "{tema_decisao["tema"]}" '
        f'({_fmt_pct(tema_decisao["pct_discurso"])} do discurso), mas o público reage pouco a '
        f'isso ({_fmt_pct(tema_decisao["pct_reacao"])} dos comentários).'
    )


# ---------------------------------------------------------------------------
# Normalização / seleção de governador (duplicado de `resumo.py`/`produzir.py`/
# `radar.py`/`comparar.py` -- mesmo raciocínio: cada tela fica autocontida,
# sem depender de outra tela nem de `src/dashboard/filters.py`, descontinuado
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
# Renderização das barras (issue #116, user story 2 -- duas colunas lado a
# lado, mesma taxonomia, mesma ordem, mesma escala 0-100%).
# ---------------------------------------------------------------------------


def _figura_barras(
    tabela_gap: pd.DataFrame, coluna: str, cor: str, titulo: str, escala_max_pct: float
) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(
        x=(tabela_gap[coluna] * 100).round(1),
        y=tabela_gap["tema"],
        orientation="h",
        marker_color=cor,
    )
    fig.update_layout(
        title=titulo,
        xaxis_title="% das menções",
        xaxis_range=[0, escala_max_pct],
        yaxis={"categoryorder": "array", "categoryarray": tabela_gap["tema"].tolist()[::-1]},
        margin={"t": 40, "b": 10, "l": 10, "r": 10},
        height=320,
    )
    return fig


def _render_barras(tabela_gap: pd.DataFrame) -> None:
    # Mesma escala de eixo X nas duas colunas (issue #116, user story 2 --
    # "comparar as duas distribuições diretamente") -- sem isso, um tema
    # dominante de um lado distorceria a impressão visual de tamanho relativo
    # do outro lado.
    maior_pct = max(
        float(tabela_gap["pct_discurso"].max()) if not tabela_gap.empty else 0.0,
        float(tabela_gap["pct_reacao"].max()) if not tabela_gap.empty else 0.0,
    )
    escala_max_pct = max(10.0, (maior_pct * 100) * 1.1)

    col_discurso, col_reacao = st.columns(2)
    with col_discurso:
        st.plotly_chart(
            _figura_barras(
                tabela_gap,
                "pct_discurso",
                COLORS["info"]["fg"],
                "Do que a assessoria fala",
                escala_max_pct,
            ),
            width="stretch",
        )
    with col_reacao:
        st.plotly_chart(
            _figura_barras(
                tabela_gap,
                "pct_reacao",
                COLORS["good"]["fg"],
                "A que o público reage",
                escala_max_pct,
            ),
            width="stretch",
        )


# ---------------------------------------------------------------------------
# render()
# ---------------------------------------------------------------------------


def render() -> None:
    df_metadata = data.load_governors_metadata()
    df_discourse_all = data.load_discourse_topics()

    options = _governor_options(df_metadata)
    if not options and not df_discourse_all.empty and "inputUrl" in df_discourse_all.columns:
        urls = df_discourse_all["inputUrl"].dropna().unique().tolist()
        options = {url: url for url in urls}
    if not options:
        df_engagement = data.load_engagement()
        if not df_engagement.empty and "inputUrl" in df_engagement.columns:
            urls = df_engagement["inputUrl"].dropna().unique().tolist()
            options = {url: url for url in urls}

    if not options:
        st.selectbox("Governador", options=[_PLACEHOLDER_SEM_GOVERNADOR], disabled=True)
        stage_label(_STAGE)
        st.info(
            "Nenhum governador disponível ainda -- rode a pipeline "
            "(`uv run python pipeline.py`) para popular o dashboard."
        )
        footnote()
        return

    nome_selecionado = st.selectbox("Governador", options=list(options.keys()))
    governor_url = options[nome_selecionado]
    stage_label(_STAGE)

    # ---- Discurso (nunca calcula gap com metade do dado ausente) ----
    df_discurso_governador = _filtrar_por_governador(df_discourse_all, governor_url)
    if df_discurso_governador.empty:
        st.info(
            "Dados de discurso ainda não disponíveis para este governador -- "
            "rode `scripts/run_modeling.py` (estágio de discurso) para gerá-los."
        )
        footnote()
        return

    # ---- Reação (comentários) ----
    df_reacao_governador = _filtrar_por_governador(
        data.comments_only(data.load_sentiment()), governor_url
    )
    if df_reacao_governador.empty:
        st.caption(
            "Sem comentários suficientes para este governador ainda -- a "
            "coluna de reação abaixo ficará zerada até haver dado."
        )

    dist_discurso = _distribuicao_percentual_por_tema(df_discurso_governador)
    dist_reacao = _distribuicao_percentual_por_tema(df_reacao_governador)
    tabela_gap = _montar_tabela_gap(dist_discurso, dist_reacao)

    tema_produzir = _tema_produzir_mais(tabela_gap)
    tema_reduzir = _tema_reduzir_reformular(tabela_gap)
    tema_decisao = _tema_decisao(tema_produzir, tema_reduzir)

    # ---- Frase de decisão (sempre "warn" -- é um descompasso, nunca uma
    # crise nem um "tudo certo", ver issue #116, Implementation Decisions) ----
    decision_band(_frase_decisao(tema_decisao), level="warn" if tema_decisao else "info")

    # ---- Barras lado a lado ----
    st.markdown("#### Discurso vs. reação, por tema")
    _render_barras(tabela_gap)
    st.caption(
        "Taxonomia curada projetando dois modelos BERTopic distintos (discurso e "
        'comentário) num conjunto comum de temas -- "outros" agrupa tópicos sem '
        "tema claro ou ainda não curados. Ver docstring do módulo para a metodologia."
    )

    # ---- Leitura automática ----
    st.markdown("#### Leitura automática")
    st.write(_frase_produzir_mais(tema_produzir))
    st.write(_frase_reduzir_reformular(tema_reduzir))

    footnote()
