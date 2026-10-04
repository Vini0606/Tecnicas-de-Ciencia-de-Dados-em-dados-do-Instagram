"""Testes do contêiner do Resumo (ADR 0031 / issue #183): seletor único,
três sub-abas na ordem NSM -> Funil -> Scorecard, Funil fora da navegação e
gráficos de evidência removidos. `render()` não é exercitado (o repo não usa
`AppTest`); a estrutura é verificada por inspeção de fonte/AST."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from dashboard.screens import resumo, resumo_funil, resumo_nsm, resumo_scorecard

_DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard"


def test_subabas_na_ordem_nsm_funil_scorecard_com_nsm_padrao():
    assert list(resumo.SUBABAS) == [
        resumo.SUBABA_NSM,
        resumo.SUBABA_FUNIL,
        resumo.SUBABA_SCORECARD,
    ]
    assert resumo.SUBABAS[resumo.SUBABA_NSM] is resumo_nsm.render
    assert resumo.SUBABAS[resumo.SUBABA_FUNIL] is resumo_funil.render
    assert resumo.SUBABAS[resumo.SUBABA_SCORECARD] is resumo_scorecard.render


def test_render_usa_seletor_unico_e_radio_sem_indice_explicito_para_padrao_nsm():
    codigo = inspect.getsource(resumo.render)
    assert codigo.count("_selecionar_governador()") == 1
    assert "index=" not in codigo  # padrao = primeira opcao (NSM)


def test_cada_subaba_aceita_o_governador_do_seletor_unico():
    for fn in resumo.SUBABAS.values():
        assert list(inspect.signature(fn).parameters) == ["governor_url"]
    # nenhuma sub-aba cria o proprio seletor de governador
    for modulo in (resumo_nsm, resumo_funil, resumo_scorecard):
        assert 'st.selectbox("Governador"' not in inspect.getsource(modulo)


def test_scorecard_e_placeholder_em_construcao():
    assert "em construção" in resumo_scorecard.AVISO_EM_CONSTRUCAO


def test_abrir_subaba_e_callback_de_session_state(monkeypatch):
    estado: dict = {}
    monkeypatch.setattr(resumo.st, "session_state", estado)
    resumo.abrir_subaba(resumo.SUBABA_FUNIL)
    assert estado[resumo.CHAVE_SUBABA] == resumo.SUBABA_FUNIL


def test_funil_nao_esta_mais_na_navegacao_lateral():
    tree = ast.parse((_DASHBOARD / "app.py").read_text(encoding="utf-8"))
    telas = next(
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "TELAS"
    )
    chaves = [k.value for k in telas.keys]
    assert "Funil de engajamento" not in chaves
    assert chaves[0] == "Resumo da semana"
    importados = {
        a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names
    }
    assert "funil" not in importados


def test_nenhuma_tela_aponta_para_a_tela_funil_removida():
    # Nenhum literal "Funil de engajamento" fora do registro de sub-abas do
    # Resumo (um alvo de `tela_selecionada` com esse rotulo quebraria o radio).
    for arquivo in (_DASHBOARD / "screens").glob("*.py"):
        if arquivo.name == "resumo.py":
            continue
        tree = ast.parse(arquivo.read_text(encoding="utf-8"))
        literais = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)]
        assert "Funil de engajamento" not in literais, arquivo.name


def test_resumo_nao_referencia_os_graficos_de_evidencia():
    proibidos = (
        "_grafico_evidencia_desempenho",
        "_renderizar_grafico_evidencia",
        "_serie_desempenho_por_publicacao",
        "_conteudo_do_governador_por_tipo",
        "resumo_metrica_desempenho",
        "TIPO_AMBOS",
        "METRICA_QUANTIDADE",
        "Evidência histórica",
    )
    for modulo in (resumo, resumo_nsm, resumo_funil, resumo_scorecard):
        fonte = inspect.getsource(modulo)
        for nome in proibidos:
            assert nome not in fonte, (modulo.__name__, nome)
