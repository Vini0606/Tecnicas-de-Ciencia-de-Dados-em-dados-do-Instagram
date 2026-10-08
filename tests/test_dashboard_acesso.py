"""Testes do portão de senha do dashboard (ADR 0037)."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from dashboard.core import acesso
from dashboard.core.acesso import (
    BLOQUEADO,
    LIBERADO,
    PEDIR_SENHA,
    decidir_acesso,
    host_local,
    senha_confere,
)

# ------------------------------------------------------------------ puras


def test_senha_confere_so_com_a_senha_exata():
    assert senha_confere("segredo", "segredo") is True
    assert senha_confere("Segredo", "segredo") is False
    assert senha_confere("", "segredo") is False
    assert senha_confere("segredo ", "segredo") is False


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "localhost:8501",
        "LOCALHOST:8501",
        "127.0.0.1",
        "127.0.0.1:8501",
        "[::1]",
        "[::1]:8501",
    ],
)
def test_host_local_reconhece_localhost(host):
    assert host_local(host) is True


@pytest.mark.parametrize(
    "host",
    [
        None,
        "",
        "app.streamlit.app",
        "localhost.evil.com",
        "127.0.0.1.evil.com",
        "evil.com:8501",
        "192.168.1.31:8501",
    ],
)
def test_host_local_rejeita_qualquer_outro_host(host):
    assert host_local(host) is False


def test_com_senha_configurada_sempre_pede_ate_entrar():
    assert decidir_acesso("s", "app.streamlit.app", liberado=False) == PEDIR_SENHA
    assert decidir_acesso("s", "localhost:8501", liberado=False) == PEDIR_SENHA
    assert decidir_acesso("s", "app.streamlit.app", liberado=True) == LIBERADO


def test_sem_senha_libera_so_no_localhost():
    assert decidir_acesso(None, "localhost:8501", liberado=False) == LIBERADO
    assert decidir_acesso(None, "app.streamlit.app", liberado=False) == BLOQUEADO
    assert decidir_acesso(None, None, liberado=False) == BLOQUEADO
    # `liberado` de uma sessão não abre um deploy sem senha configurada
    assert decidir_acesso(None, "app.streamlit.app", liberado=True) == BLOQUEADO


def test_senha_vazia_ou_so_espacos_conta_como_nao_configurada(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "   ")
    monkeypatch.setattr(acesso, "_secrets", dict)
    assert acesso.senha_configurada() is None


def test_senha_vem_do_ambiente_ou_dos_secrets(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setattr(acesso, "_secrets", lambda: {"APP_PASSWORD": " de-secrets "})
    assert acesso.senha_configurada() == "de-secrets"
    monkeypatch.setenv("APP_PASSWORD", "do-ambiente")
    assert acesso.senha_configurada() == "do-ambiente"


# -------------------------------------------------- app inteiro (AppTest)


def _app() -> AppTest:
    return AppTest.from_file("dashboard/app.py", default_timeout=120)


def test_app_com_senha_mostra_so_o_formulario_e_nenhuma_tela(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "segredo-de-teste")
    at = _app().run()
    assert not at.exception
    assert [t.label for t in at.text_input] == ["Senha"]
    assert len(at.radio) == 0  # nem a navegação das telas é renderizada
    assert len(at.selectbox) == 0


def test_senha_errada_mantem_bloqueado_e_avisa(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "segredo-de-teste")
    monkeypatch.setattr(acesso, "ATRASO_SENHA_ERRADA", 0)
    at = _app().run()
    at.text_input[0].input("errada")
    at.button[0].click()
    at.run()
    assert not at.exception
    assert [e.value for e in at.error] == ["Senha incorreta."]
    assert len(at.radio) == 0


def test_senha_certa_libera_o_app(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "segredo-de-teste")
    at = _app().run()
    at.text_input[0].input("segredo-de-teste")
    at.button[0].click()
    at.run()
    assert not at.exception
    assert len(at.text_input) == 0
    assert "Telas" in [r.label for r in at.radio]


def test_sem_senha_fora_do_localhost_bloqueia_o_app(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setattr(acesso, "_secrets", dict)
    monkeypatch.setattr(acesso, "_host_da_requisicao", lambda: "app.streamlit.app")
    at = _app().run()
    assert not at.exception
    assert any("APP_PASSWORD" in e.value for e in at.error)
    assert len(at.radio) == 0
