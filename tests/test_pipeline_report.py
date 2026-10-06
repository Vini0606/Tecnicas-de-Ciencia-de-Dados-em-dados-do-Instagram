"""Issue #214: relatório de tabelas esperadas ao final do pipeline.py."""

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from deltalake import write_deltalake

from src.pipeline_report import (
    TABELAS_ESPERADAS,
    Status,
    TabelaEsperada,
    avaliar_tabelas,
    codigo_de_saida,
    formatar_relatorio,
    ler_ultimo_commit,
    contar_linhas,
)

ROOT = Path(__file__).resolve().parent.parent
INICIO = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def _tabela(nome, estagio="gold", dashboard=True):
    return TabelaEsperada(nome, Path(nome), estagio, dashboard)


def _avaliar(tabelas, commits, linhas, estagios=("silver", "gold", "ugc", "modelagem")):
    return avaliar_tabelas(
        tabelas,
        INICIO,
        set(estagios),
        ler_ultimo_commit=lambda path: commits.get(str(path)),
        contar_linhas=lambda path: linhas.get(str(path), 0),
    )


def test_avaliar_tabelas_classifica_os_cinco_status():
    depois = INICIO + timedelta(minutes=5)
    antes = INICIO - timedelta(days=1)
    tabelas = [
        _tabela("ok"),
        _tabela("ausente"),
        _tabela("vazia"),
        _tabela("velha"),
        _tabela("modelo", estagio="modelagem"),
    ]

    resultado = _avaliar(
        tabelas,
        commits={"ok": depois, "vazia": depois, "velha": antes, "modelo": depois},
        linhas={"ok": 3, "velha": 3, "modelo": 3},
        estagios=("silver", "gold", "ugc"),
    )

    assert [r.status for r in resultado] == [
        Status.OK,
        Status.AUSENTE,
        Status.VAZIA,
        Status.DESATUALIZADA,
        Status.NAO_SOLICITADA,
    ]


def test_desatualizada_tem_precedencia_sobre_vazia():
    resultado = _avaliar(
        [_tabela("velha_e_vazia")],
        commits={"velha_e_vazia": INICIO - timedelta(hours=1)},
        linhas={},
    )

    assert resultado[0].status is Status.DESATUALIZADA


def test_nao_solicitada_nao_le_a_tabela():
    lidas = []

    avaliar_tabelas(
        [_tabela("modelo", estagio="modelagem")],
        INICIO,
        {"silver", "gold", "ugc"},
        ler_ultimo_commit=lambda path: lidas.append(path),
        contar_linhas=lambda path: lidas.append(path),
    )

    assert lidas == []


def test_codigo_de_saida_falha_so_por_tabela_do_dashboard():
    """Tabelas que o dashboard não lê (ex.: performance-por-post, que a ADR
    0019 pula legitimamente com pouco dado) viram aviso, não falha."""
    depois = INICIO + timedelta(minutes=1)
    ok = _avaliar(
        [_tabela("tela"), _tabela("auxiliar", dashboard=False)],
        commits={"tela": depois},
        linhas={"tela": 1},
    )
    falha = _avaliar([_tabela("tela")], commits={}, linhas={})

    assert codigo_de_saida(ok) == 0
    assert codigo_de_saida(falha) == 1


def test_codigo_de_saida_zero_com_modelagem_nao_solicitada():
    resultado = _avaliar(
        [_tabela("modelo", estagio="modelagem")], commits={}, linhas={}, estagios=("gold",)
    )

    assert codigo_de_saida(resultado) == 0


def test_formatar_relatorio_lista_tabelas_sem_emoji_e_aponta_o_log():
    resultado = _avaliar(
        [_tabela("governor_nsm"), _tabela("auxiliar", dashboard=False)], commits={}, linhas={}
    )

    texto = formatar_relatorio(resultado, Path("data/logs/run_x"))

    assert "governor_nsm" in texto and "AUSENTE" in texto
    assert "data" in texto and "run_x" in texto
    texto.encode("cp1252")


def test_leitores_reais_sobre_delta_em_tmp_path(tmp_path):
    antes = datetime.now(timezone.utc) - timedelta(seconds=1)
    write_deltalake(str(tmp_path / "cheia"), pd.DataFrame({"a": [1, 2, 3]}))
    write_deltalake(str(tmp_path / "vazia"), pd.DataFrame({"a": pd.Series([], dtype="int64")}))

    assert ler_ultimo_commit(tmp_path / "cheia") >= antes
    assert ler_ultimo_commit(tmp_path / "inexistente") is None
    assert contar_linhas(tmp_path / "cheia") == 3
    assert contar_linhas(tmp_path / "vazia") == 0


def test_tabela_escrita_antes_do_inicio_fica_desatualizada(tmp_path):
    write_deltalake(str(tmp_path / "velha"), pd.DataFrame({"a": [1]}))
    inicio = datetime.now(timezone.utc) + timedelta(seconds=1)
    tabelas = [TabelaEsperada("velha", tmp_path / "velha", "gold", True)]

    resultado = avaliar_tabelas(tabelas, inicio, {"gold"}, ler_ultimo_commit, contar_linhas)

    assert resultado[0].status is Status.DESATUALIZADA


def test_catalogo_cobre_as_tabelas_gravadas_pelo_pipeline():
    nomes = {t.nome for t in TABELAS_ESPERADAS}

    assert {
        "post_comments_clean",
        "ugc_mentions",
        "governor_ugc_mentions",
        "governor_scorecard",
        "content_topic_priority_score",
    } <= nomes
    assert len(nomes) == len(TABELAS_ESPERADAS)


def _tabelas_lidas_pelas_telas():
    """Tabelas alcançáveis a partir das Telas: `load_*` de dashboard/core/data.py
    chamados em dashboard/app.py ou dashboard/screens/*.py -> método do
    DeltaRepository chamado nesse loader -> literais passados a `_join`."""
    data_tree = ast.parse((ROOT / "dashboard/core/data.py").read_text(encoding="utf-8"))
    repo_tree = ast.parse(
        (ROOT / "src/repositories/delta_repository.py").read_text(encoding="utf-8")
    )

    def chamadas(node):
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func = sub.func
                yield func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)

    loaders = {f.name: f for f in data_tree.body if isinstance(f, ast.FunctionDef)}
    repo_methods = {
        f.name: f
        for cls in repo_tree.body
        if isinstance(cls, ast.ClassDef)
        for f in cls.body
        if isinstance(f, ast.FunctionDef)
    }

    usados = set()
    for arquivo in [ROOT / "dashboard/app.py", *sorted((ROOT / "dashboard/screens").glob("*.py"))]:
        usados |= set(chamadas(ast.parse(arquivo.read_text(encoding="utf-8")))) & set(loaders)

    tabelas = set()
    for loader in usados:
        for metodo in set(chamadas(loaders[loader])) & set(repo_methods):
            for sub in ast.walk(repo_methods[metodo]):
                if isinstance(sub, ast.Call) and getattr(sub.func, "id", None) == "_join":
                    literal = sub.args[1]
                    if isinstance(literal, ast.Constant):
                        tabelas.add(literal.value)
    return tabelas


def test_anti_deriva_catalogo_bate_com_as_tabelas_lidas_pelas_telas():
    """Uma Tela nova lendo uma tabela nova sem entrada no catálogo quebra aqui
    -- e uma tabela marcada como "do dashboard" que nenhuma Tela lê também."""
    lidas = _tabelas_lidas_pelas_telas()
    do_dashboard = {t.nome for t in TABELAS_ESPERADAS if t.usada_pelo_dashboard}

    assert lidas, "nenhuma tabela encontrada -- a análise estática quebrou"
    assert lidas == do_dashboard


def test_relatorio_final_do_pipeline_sai_com_1_e_loga_falha(tmp_path, caplog):
    import pipeline

    tabelas = [TabelaEsperada("governor_nsm", tmp_path / "governor_nsm", "modelagem", True)]

    with caplog.at_level("INFO"):
        codigo = pipeline.relatorio_final(
            INICIO, run_modeling=True, run_id="run_x", caminho_log=tmp_path, tabelas=tabelas
        )

    assert codigo == 1
    assert "[FALHA]" in caplog.text and "governor_nsm" in caplog.text


def test_relatorio_final_sem_modelagem_marca_nao_solicitada_e_sai_com_0(tmp_path, caplog):
    import pipeline

    write_deltalake(str(tmp_path / "governor_engagement"), pd.DataFrame({"a": [1]}))
    tabelas = [
        TabelaEsperada("governor_engagement", tmp_path / "governor_engagement", "gold", True),
        TabelaEsperada("governor_nsm", tmp_path / "governor_nsm", "modelagem", True),
    ]

    with caplog.at_level("INFO"):
        codigo = pipeline.relatorio_final(
            datetime.now(timezone.utc) - timedelta(minutes=1),
            run_modeling=False,
            run_id="run_x",
            caminho_log=tmp_path,
            tabelas=tabelas,
        )

    assert codigo == 0
    assert "NAO SOLICITADA" in caplog.text
    assert "[OK] Pipeline Medallion finalizado com run_id: run_x" in caplog.text
