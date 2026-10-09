"""Rótulos de tópico legíveis e sem menções de terceiros (ADR 0038)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from dashboard.core import data, theme
from dashboard.core.rotulos import (
    extrair_mencoes,
    remover_mencoes,
    rotular_topico,
    rotulo_se_emoji,
)
from dashboard.screens import comparar, produzir, resumo_funil

# Nomes reais de tópicos de comentário (governor_sentiment, 2026-10).
_EMOJI_REAIS = {
    "0_mãos_aplaudindo_mãos_aplaudindo_pele_clara_mãos_aplaudindo_pele_escura": "Emojis de mãos e aplausos",
    "-1_tecla_3_tecla_2_tecla_1_tecla_0": "Emojis de números",
    "1_tecla_5_tecla_1_tecla_4_tecla_7": "Emojis de números",
    "2_tecla_5_coração_azul_tecla_1_tecla_2": "Emojis de números",
    "3_rosto_chorando_de_rir_rosto_chorando_rosto_chorando_aos_berros": "Emojis de rostos",
    "4_coração_vermelho_coração_verde_coração_laranja_coração_amarelo": "Emojis de corações",
    "8_rosto_sorridente_com_olhos_de_coração_rosto_risonho_com_olhos_sorridentes": "Emojis de rostos",
    "9_mãos_para_cima_mãos_juntas_seta_para_cima_e_para_a_direita": "Emojis de mãos e aplausos",
}
_TEXTO_REAL = [
    "6_precisando_precisamos_poupando_absurdo",
    "10_foguete_balão_hélder_estourou",
    "11_parabéns_parabens_admiro_agradecer",
    "25_defendam_incontestáveis_reconheço_227",
]


@pytest.mark.parametrize(("nome", "esperado"), list(_EMOJI_REAIS.items()))
def test_topicos_de_emoji_ganham_nome_legivel(nome, esperado):
    assert rotulo_se_emoji(nome) == esperado
    assert rotular_topico(nome) == esperado


@pytest.mark.parametrize("nome", _TEXTO_REAL)
def test_topicos_de_texto_nao_viram_emoji(nome):
    assert rotulo_se_emoji(nome) is None


def test_rotular_topico_tira_o_prefixo_de_id_e_troca_underscore_por_virgula():
    assert (
        rotular_topico("25_defendam_incontestáveis_reconheço_227")
        == "defendam, incontestáveis, reconheço, 227"
    )
    assert rotular_topico("-1_a_b") == "a, b"


def test_rotular_topico_trunca_nomes_longos_e_tolera_nulo_e_vazio():
    longo = "1_" + "_".join(f"palavra{i}" for i in range(40))
    assert len(rotular_topico(longo)) <= 60
    assert rotular_topico(longo).endswith("…")
    for vazio in (None, float("nan"), "", "7_"):
        assert rotular_topico(vazio) == "Tema sem rótulo definido"


def test_bandeira_do_brasil_com_coracoes_conta_como_emoji_mas_texto_com_um_emoji_nao():
    assert (
        rotulo_se_emoji("12_bandeira_brasil_brasil_coração_verde_coração_vermelho")
        is not None
    )
    assert rotulo_se_emoji("3_coração_cheio_de_gratidão_deus") is None


# ------------------------------------------------------------------ menções


def test_extrair_mencoes_pega_so_usuarios_longos_em_minusculas():
    textos = [
        "oi @ArthurHenriqueRR e @boavistaroraima.",
        "@brasil @ab sem mencao",
        None,
        5,
    ]
    assert extrair_mencoes(textos) == frozenset({"arthurhenriquerr", "boavistaroraima"})


def test_remover_mencoes_no_formato_de_pauta_e_no_formato_bruto():
    mencoes = frozenset({"arthurhenriquerr", "boavistaroraima"})
    assert (
        remover_mencoes(
            "parabéns, arthurhenriquerr, boavistaroraima, abençoando", mencoes
        )
        == "parabéns, abençoando"
    )
    assert remover_mencoes("11_ola_arthurhenriquerr_x", mencoes) == "11_ola_x"


def test_remover_mencoes_nunca_tira_o_id_nem_devolve_nome_vazio_nem_quebra():
    assert remover_mencoes("7_a_b", frozenset({"7"})) == "7_a_b"
    assert (
        remover_mencoes("arthurhenriquerr", frozenset({"arthurhenriquerr"}))
        == "arthurhenriquerr"
    )
    assert remover_mencoes("a, b", frozenset()) == "a, b"
    assert remover_mencoes(None, frozenset({"x" * 8})) is None


# ------------------------------------------------- integração nos loaders


class _RepoFake:
    def load_comments(self):
        return pd.DataFrame(
            {
                "text": ["valeu @arthurhenriquerr", "viva @helderoficial, parabéns"],
                "Name": ["1_a_arthurhenriquerr_b", "2_helderoficial_c"],
            }
        )

    def load_discourse_topics(self):
        return pd.DataFrame(
            {"text": ["com @boavistaroraima"], "Name": ["0_x_boavistaroraima"]}
        )

    def load_governors_metadata(self):
        return pd.DataFrame({"inputUrl": ["https://www.instagram.com/HelderOficial/"]})


def test_mencoes_de_terceiros_ignora_os_perfis_dos_governadores(monkeypatch):
    import streamlit as st

    st.cache_data.clear()
    monkeypatch.setattr(data, "get_repository", lambda: _RepoFake())
    assert data.mencoes_de_terceiros() == frozenset(
        {"arthurhenriquerr", "boavistaroraima"}
    )
    st.cache_data.clear()


def test_sem_mencoes_limpa_a_coluna_name_e_preserva_o_resto(monkeypatch):
    monkeypatch.setattr(
        data, "mencoes_de_terceiros", lambda: frozenset({"arthurhenriquerr"})
    )
    df = pd.DataFrame({"Name": ["1_a_arthurhenriquerr_b"], "outra": [5]})
    out = data._sem_mencoes(df)
    assert out["Name"].tolist() == ["1_a_b"]
    assert out["outra"].tolist() == [5]
    assert df["Name"].tolist() == ["1_a_arthurhenriquerr_b"]  # não altera a entrada
    sem_name = pd.DataFrame({"x": [1]})
    assert data._sem_mencoes(sem_name) is sem_name
    vazio = pd.DataFrame()
    assert data._sem_mencoes(vazio) is vazio


# ----------------------------------------------------- telas e configuração


def test_grupo_de_comentarios_de_emoji_usa_o_nome_legivel():
    assert (
        produzir._rotulo_grupo("0_mãos_aplaudindo_pele_clara")
        == "Emojis de mãos e aplausos"
    )
    assert produzir._rotulo_grupo("11_parabéns_parabens_admiro_agradecer") == (
        "parabéns, parabens, admiro, agradecer"
    )
    assert produzir._rotulo_grupo(None) == produzir.ROTULO_GRUPO_SEM_ROTULO


def test_aviso_de_agrupamento_nao_fixa_o_numero_de_perfis():
    assert "27" not in comparar._AVISO_EXPERIMENTAL


def test_funil_svg_tem_descricao_acessivel():
    estagios = (1_000.0, 100.0, 10.0)
    html = resumo_funil._html_funil(
        estagios, resumo_funil._taxas_passagem(*estagios), None
    )
    assert 'role="img"' in html
    assert (
        'aria-label="Funil em escala logarítmica: Reach 1.000, Act 100, Convert 10"'
        in html
    )


def test_streamlit_sem_telemetria_de_uso():
    config = Path(".streamlit/config.toml").read_text(encoding="utf-8")
    assert "[browser]" in config
    assert "gatherUsageStats = false" in config


def test_pagina_declara_idioma_pt_br_e_falha_em_silencio(monkeypatch):
    assert "pt-BR" in theme._SCRIPT_IDIOMA

    def quebra(*_a, **_k):
        raise RuntimeError("sem componente")

    monkeypatch.setattr(theme.components, "html", quebra)
    theme._definir_idioma()  # não lança


def test_iframe_do_idioma_nao_deixa_vao_na_tela():
    """O contêiner do iframe de altura 0 ainda ocupava 16 px (espaçamento do bloco
    vertical): a regra de CSS precisa casar com o `srcdoc` do próprio iframe."""
    fonte = Path("dashboard/core/theme.py").read_text(encoding="utf-8")
    assert 'iframe[srcdoc*="documentElement.lang"]' in fonte
    assert "documentElement.lang" in theme._SCRIPT_IDIOMA
