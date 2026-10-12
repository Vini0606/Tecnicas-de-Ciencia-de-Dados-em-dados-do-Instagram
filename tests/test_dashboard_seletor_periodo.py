from streamlit.testing.v1 import AppTest


def _app():
    import datetime as dt

    import streamlit as st

    from dashboard.core.seletor_periodo import seletor_periodo

    inicio, fim = seletor_periodo((dt.date(2026, 8, 1), dt.date(2026, 9, 1)))
    st.write(f"{inicio}|{fim}")


def _saida(at):
    return at.markdown[0].value


def test_seletor_comeca_em_todo_o_periodo():
    at = AppTest.from_function(_app).run()
    assert not at.exception
    assert _saida(at) == "2026-08-01|2026-09-01"


def test_seletor_aceita_intervalo_digitado_e_preso_aos_limites():
    at = AppTest.from_function(_app).run()
    at.text_input[0].set_value("de 10/08/2026 até 20/12/2026").run()
    assert not at.exception
    assert _saida(at) == "2026-08-10|2026-09-01"


def test_seletor_texto_invalido_mantem_periodo_e_avisa():
    at = AppTest.from_function(_app).run()
    at.text_input[0].set_value("ontem").run()
    assert _saida(at) == "2026-08-01|2026-09-01"
    assert any("Não entendi" in c.value for c in at.caption)


def test_seletor_botao_todo_o_periodo_restaura():
    at = AppTest.from_function(_app).run()
    at.text_input[0].set_value("05/08/2026 até 06/08/2026").run()
    assert _saida(at) == "2026-08-05|2026-08-06"
    at.button[0].click().run()
    assert _saida(at) == "2026-08-01|2026-09-01"
