"""Testes da Tela 6 ("Funil de engajamento", ADR 0021 / issue #114).

Só a lógica pura de `dashboard/screens/funil.py` é testada aqui (agregação
por estágio, taxas de passagem, identificação do gargalo, escalonamento,
ação recomendada) -- nunca a renderização Streamlit em si, mesmo padrão de
`tests/test_dashboard_screens_{resumo,produzir,radar}.py`.

Inclui também um teste ESTÁTICO (inspeção de AST do código-fonte do módulo)
confirmando que nenhum identificador/string relacionado a UGC aparece no
código executável de `funil.py` -- ver issue #114, Testing Decisions."""

from __future__ import annotations

import ast
import inspect

import pandas as pd

from dashboard.screens import funil

_GOVERNOR_URL = "https://instagram.com/governador_a"


# ---------------------------------------------------------------------------
# _visualizacoes_reels_governador (Reach·Alcançar) -- null handling de
# `videoPlayCount` (issue #114, Testing Decisions).
# ---------------------------------------------------------------------------


def _df_clusters_reel(ids: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id_reel": ids,
            "ownerUsername": ["governador_a"] * len(ids),
            "content_type": ["reel"] * len(ids),
        }
    )


def _df_reels(ids: list[str], views: list[float | None]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": ids,
            "inputUrl": [_GOVERNOR_URL] * len(ids),
            "videoPlayCount": views,
        }
    )


def test_visualizacoes_reels_governador_soma_views_reais():
    df_clusters = _df_clusters_reel(["r1", "r2"])
    df_reels = _df_reels(["r1", "r2"], [100, 50])

    assert funil._visualizacoes_reels_governador(df_clusters, df_reels, _GOVERNOR_URL) == 150.0


def test_visualizacoes_reels_governador_exclui_nulos_da_soma_nunca_vira_nan():
    df_clusters = _df_clusters_reel(["r1", "r2", "r3"])
    df_reels = _df_reels(["r1", "r2", "r3"], [100, None, 50])

    total = funil._visualizacoes_reels_governador(df_clusters, df_reels, _GOVERNOR_URL)

    # 100 + 50 -- o reel com videoPlayCount nulo é EXCLUÍDO da soma, não
    # tratado como zero (que já daria o mesmo resultado neste caso), e o
    # total nunca é NaN.
    assert total == 150.0
    assert not pd.isna(total)


def test_visualizacoes_reels_governador_todos_nulos_retorna_zero_nunca_nan():
    df_clusters = _df_clusters_reel(["r1", "r2"])
    df_reels = _df_reels(["r1", "r2"], [None, None])

    total = funil._visualizacoes_reels_governador(df_clusters, df_reels, _GOVERNOR_URL)

    assert total == 0.0
    assert not pd.isna(total)


def test_visualizacoes_reels_governador_tabelas_vazias_retorna_zero():
    assert funil._visualizacoes_reels_governador(pd.DataFrame(), pd.DataFrame(), _GOVERNOR_URL) == 0.0


def test_visualizacoes_reels_governador_ignora_conteudo_que_nao_e_reel():
    df_clusters = pd.DataFrame(
        {
            "id_reel": ["p1"],
            "ownerUsername": ["governador_a"],
            "content_type": ["feed"],
        }
    )
    df_reels = _df_reels(["p1"], [999])

    # `p1` não tem cluster `content_type == 'reel'` -- não é encontrado no
    # merge, soma fica em 0.0 (não em 999, que seria de um post de feed).
    assert funil._visualizacoes_reels_governador(df_clusters, df_reels, _GOVERNOR_URL) == 0.0


# ---------------------------------------------------------------------------
# _consumir_likes_governador (Act·Consumir)
# ---------------------------------------------------------------------------


def test_consumir_likes_governador_le_likes_sum():
    df_engagement = pd.DataFrame({"inputUrl": [_GOVERNOR_URL], "likesSum": [500]})
    assert funil._consumir_likes_governador(df_engagement, _GOVERNOR_URL) == 500.0


def test_consumir_likes_governador_sem_match_retorna_zero():
    df_engagement = pd.DataFrame({"inputUrl": ["https://instagram.com/outro"], "likesSum": [500]})
    assert funil._consumir_likes_governador(df_engagement, _GOVERNOR_URL) == 0.0


# ---------------------------------------------------------------------------
# _contribuir_comentarios_positivos_governador (Convert·Contribuir)
# ---------------------------------------------------------------------------


def test_contribuir_comentarios_positivos_conta_so_positivos():
    df_sentiment = pd.DataFrame(
        {
            "inputUrl": [_GOVERNOR_URL] * 4,
            "sentiment_label": ["positive", "positive", "negative", "neutral"],
        }
    )
    assert funil._contribuir_comentarios_positivos_governador(df_sentiment, _GOVERNOR_URL) == 2.0


def test_contribuir_comentarios_positivos_vazio_retorna_zero():
    assert funil._contribuir_comentarios_positivos_governador(pd.DataFrame(), _GOVERNOR_URL) == 0.0


# ---------------------------------------------------------------------------
# _taxas_passagem / _identificar_gargalo (issue #114, Testing Decisions:
# gargalo óbvio, empate, dado insuficiente num estágio)
# ---------------------------------------------------------------------------


def test_taxas_passagem_calcula_as_duas_taxas():
    taxas = funil._taxas_passagem(reach=1000, act=500, convert=100)
    assert taxas[funil._ESTAGIO_ACT] == 0.5
    assert taxas[funil._ESTAGIO_CONVERT] == 0.2


def test_taxas_passagem_reach_zero_taxa_act_e_none():
    taxas = funil._taxas_passagem(reach=0, act=500, convert=100)
    assert taxas[funil._ESTAGIO_ACT] is None
    # Act/Reach é None, mas Convert/Act ainda é calculável.
    assert taxas[funil._ESTAGIO_CONVERT] == 0.2


def test_taxas_passagem_act_zero_taxa_convert_e_none():
    taxas = funil._taxas_passagem(reach=1000, act=0, convert=100)
    assert taxas[funil._ESTAGIO_CONVERT] is None


def test_identificar_gargalo_caso_obvio():
    # Act/Reach = 0.1 (gargalo óbvio), Convert/Act = 0.8.
    taxas = {funil._ESTAGIO_ACT: 0.1, funil._ESTAGIO_CONVERT: 0.8}
    assert funil._identificar_gargalo(taxas) == funil._ESTAGIO_ACT


def test_identificar_gargalo_caso_de_empate_prefere_estagio_mais_cedo():
    taxas = {funil._ESTAGIO_ACT: 0.3, funil._ESTAGIO_CONVERT: 0.3}
    # Empate -- desempatado pela ordem do funil (Act antes de Convert), ver
    # docstring do módulo, decisão 6.
    assert funil._identificar_gargalo(taxas) == funil._ESTAGIO_ACT


def test_identificar_gargalo_dado_insuficiente_em_um_estagio_e_excluido_nao_zerado():
    # Act/Reach é None (dado insuficiente) -- não deve ser tratado como 0.0
    # (que venceria artificialmente); só Convert tem dado real, então é o
    # gargalo por eliminação.
    taxas = {funil._ESTAGIO_ACT: None, funil._ESTAGIO_CONVERT: 0.4}
    assert funil._identificar_gargalo(taxas) == funil._ESTAGIO_CONVERT


def test_identificar_gargalo_nenhum_dado_real_retorna_none():
    taxas = {funil._ESTAGIO_ACT: None, funil._ESTAGIO_CONVERT: None}
    assert funil._identificar_gargalo(taxas) is None


# ---------------------------------------------------------------------------
# _convert_esta_caindo / _nivel_decisao -- escalonamento independente do
# gargalo (issue #114, Implementation Decisions)
# ---------------------------------------------------------------------------


def test_agregar_positivos_por_run_conta_por_execucao():
    df = pd.DataFrame(
        {
            "sentiment_label": ["positive", "negative", "positive", "positive"],
            "_run_id": ["r1", "r1", "r2", "r2"],
        }
    )
    agregado = funil._agregar_positivos_por_run(df)
    valores = dict(zip(agregado["_run_id"], agregado["qtd_positivos"], strict=True))
    assert valores == {"r1": 1, "r2": 2}


_CHAVE = funil._CHAVE_GOVERNADOR_UNICO


def test_convert_esta_caindo_true_quando_contagem_cai():
    df = pd.DataFrame(
        {"_chave": [_CHAVE, _CHAVE], "_run_id": ["r1", "r2"], "qtd_positivos": [10, 5]}
    )
    assert funil._convert_esta_caindo(df) is True


def test_convert_esta_caindo_false_quando_contagem_sobe():
    df = pd.DataFrame(
        {"_chave": [_CHAVE, _CHAVE], "_run_id": ["r1", "r2"], "qtd_positivos": [5, 10]}
    )
    assert funil._convert_esta_caindo(df) is False


def test_convert_esta_caindo_false_sem_historico_suficiente():
    df = pd.DataFrame({"_chave": [_CHAVE], "_run_id": ["r1"], "qtd_positivos": [5]})
    assert funil._convert_esta_caindo(df) is False


def test_nivel_decisao_escalona_para_warn_mesmo_sem_gargalo_absoluto():
    # Nenhum gargalo identificável (dado insuficiente), mas Convert caindo
    # -- ainda assim "warn" (issue #114: "subir a faixa de decisão para
    # amarelo mesmo que não seja o menor valor absoluto").
    assert funil._nivel_decisao(gargalo=None, convert_caindo=True) == "warn"


def test_nivel_decisao_warn_quando_ha_gargalo():
    assert funil._nivel_decisao(gargalo=funil._ESTAGIO_ACT, convert_caindo=False) == "warn"


def test_nivel_decisao_info_sem_gargalo_e_sem_queda():
    assert funil._nivel_decisao(gargalo=None, convert_caindo=False) == "info"


# ---------------------------------------------------------------------------
# _frase_decisao -- linguagem associativa, nunca causal (user story 8)
# ---------------------------------------------------------------------------


def test_frase_decisao_nunca_usa_linguagem_causal():
    frases = [
        funil._frase_decisao(gargalo=None, convert_caindo=False),
        funil._frase_decisao(gargalo=funil._ESTAGIO_ACT, convert_caindo=False),
        funil._frase_decisao(gargalo=funil._ESTAGIO_CONVERT, convert_caindo=False),
        funil._frase_decisao(gargalo=funil._ESTAGIO_CONVERT, convert_caindo=True),
    ]
    for frase in frases:
        assert "causa" not in frase.lower()
        assert " gera " not in frase.lower()


def test_frase_decisao_nomeia_o_estagio_gargalo():
    frase = funil._frase_decisao(gargalo=funil._ESTAGIO_CONVERT, convert_caindo=False)
    assert "contribuir" in frase.lower()


# ---------------------------------------------------------------------------
# _acao_recomendada -- negatividade em alta tem prioridade sobre o gargalo
# (issue #114, user story 6)
# ---------------------------------------------------------------------------


def test_acao_recomendada_negatividade_em_alta_aponta_para_radar():
    acao = funil._acao_recomendada(gargalo=funil._ESTAGIO_CONVERT, negatividade_em_alta=True)
    assert acao["alvo"] == funil._ACAO_RADAR
    assert acao["label_botao"] == f"Ver {funil._LABEL_TELA_RADAR}"


def test_acao_recomendada_gargalo_convert_aponta_para_produzir():
    acao = funil._acao_recomendada(gargalo=funil._ESTAGIO_CONVERT, negatividade_em_alta=False)
    assert acao["alvo"] == funil._ACAO_PRODUZIR


def test_acao_recomendada_gargalo_act_aponta_para_produzir():
    acao = funil._acao_recomendada(gargalo=funil._ESTAGIO_ACT, negatividade_em_alta=False)
    assert acao["alvo"] == funil._ACAO_PRODUZIR


def test_acao_recomendada_none_quando_nada_para_recomendar():
    assert funil._acao_recomendada(gargalo=None, negatividade_em_alta=False) is None


def test_acao_recomendada_texto_nunca_usa_linguagem_causal():
    acao = funil._acao_recomendada(gargalo=funil._ESTAGIO_ACT, negatividade_em_alta=False)
    assert "causa" not in acao["texto"].lower()
    assert " gera " not in acao["texto"].lower()


# ---------------------------------------------------------------------------
# Proibição estrutural de UGC (issue #114, Testing Decisions) -- inspeção de
# AST do código-fonte de `funil.py`: nenhum identificador/string de código
# (fora de docstrings) contém "ugc".
# ---------------------------------------------------------------------------


def test_funil_module_never_references_ugc_tables():
    source = inspect.getsource(funil)
    tree = ast.parse(source)

    docstring_const_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstring_const_ids.add(id(body[0].value))

    suspeitos: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and "ugc" in node.id.lower():
            suspeitos.append(f"Name:{node.id}")
        elif isinstance(node, ast.Attribute) and "ugc" in node.attr.lower():
            suspeitos.append(f"Attribute:{node.attr}")
        elif isinstance(node, ast.alias):
            if "ugc" in node.name.lower() or (node.asname and "ugc" in node.asname.lower()):
                suspeitos.append(f"alias:{node.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and "ugc" in node.name.lower():
            suspeitos.append(f"def:{node.name}")
        elif isinstance(node, ast.arg) and "ugc" in node.arg.lower():
            suspeitos.append(f"arg:{node.arg}")
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstring_const_ids
            and "ugc" in node.value.lower()
        ):
            suspeitos.append(f"str:{node.value}")

    assert not suspeitos, f"Identificadores/strings relacionados a UGC encontrados: {suspeitos}"


def test_funil_module_does_not_import_ugc_loader_or_aggregator():
    """Confirmação comportamental complementar ao teste estático acima:
    `dashboard.screens.funil` não tem nenhum atributo cujo nome comece com
    `load_ugc`/`aggregate_ugc` -- nem por importação direta, nem por acesso
    via `dashboard.core.data`/`src.dashboard.filters`."""
    atributos = dir(funil)
    assert not any(nome.lower().startswith(("load_ugc", "aggregate_ugc")) for nome in atributos)
