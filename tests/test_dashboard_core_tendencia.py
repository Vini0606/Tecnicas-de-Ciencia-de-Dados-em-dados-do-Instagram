"""Testes do nucleo da Tendencia (ADR 0040 / issue #285) -- funcoes puras com
DataFrames. Metodo e limiares PROVISORIOS (aguardam o backtest #284)."""

import inspect

import numpy as np
import pandas as pd

from dashboard.core import tendencia as tend


def _datas(n, passo=2):
    base = pd.Timestamp("2026-01-01")
    return [base + pd.Timedelta(days=passo * i) for i in range(n)]


def _serie_valor(n=40, efeito=0.0, ruido=0.1, seed=0):
    """Valor com tendencia log-linear de `efeito` (fracao ao longo da serie)."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 1, n)
    y = 100 * np.exp(np.log1p(efeito) * t + rng.normal(0, ruido, n))
    return pd.DataFrame({"data": _datas(n), "valor": y})


def _serie_prop(n=40, efeito=0.0, seed=0, total=60):
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 1, n)
    p = np.clip(0.3 * (1 + efeito * t), 0.01, 0.95)
    tot = rng.integers(total // 2, total * 2, n)
    k = rng.binomial(tot, p)
    return pd.DataFrame({"data": _datas(n), "positivos": k, "total": tot})


def test_constantes_provisorias_estao_marcadas():
    fonte = inspect.getsource(tend)
    assert fonte.count("PROVISÓRIO (ADR 0040, aguarda #284)") >= 4


def test_valor_tendencia_clara_de_alta_e_queda():
    sobe = tend.tendencia_valor(_serie_valor(efeito=0.6))
    assert sobe.estado == tend.SUBINDO
    assert 0.3 < sobe.variacao < 1.0
    assert sobe.ic_inferior > 0
    cai = tend.tendencia_valor(_serie_valor(efeito=-0.4, seed=1))
    assert cai.estado == tend.CAINDO
    assert cai.variacao < -0.2 and cai.ic_superior < 0


def test_valor_serie_plana_com_ruido_e_estavel():
    r = tend.tendencia_valor(_serie_valor(efeito=0.0, ruido=0.3, seed=3))
    assert r.estado == tend.ESTAVEL
    assert r.ic_inferior < 0 < r.ic_superior


def test_valor_serie_curta_ou_poucos_dias_e_dados_insuficientes():
    curta = tend.tendencia_valor(_serie_valor(n=5, efeito=1.0))
    assert curta.estado == tend.INSUFICIENTE
    assert curta.variacao is None and curta.ic_inferior is None
    # muitas linhas, mas em poucos dias distintos
    df = _serie_valor(n=30, efeito=1.0)
    df["data"] = _datas(3, 1) * 10
    assert tend.tendencia_valor(df).estado == tend.INSUFICIENTE


def test_valor_serie_vazia_sem_colunas_e_nulos():
    assert tend.tendencia_valor(pd.DataFrame()).estado == tend.INSUFICIENTE
    vazia = pd.DataFrame(columns=["data", "valor"])
    assert tend.tendencia_valor(vazia).estado == tend.INSUFICIENTE
    df = _serie_valor(efeito=0.6)
    com_nulos = df.copy()
    com_nulos.loc[com_nulos.index[::4], "valor"] = np.nan  # 10 nulos
    com_nulos.loc[com_nulos.index[1], "data"] = pd.NaT  # 1 data nula
    r = tend.tendencia_valor(com_nulos)
    assert r.estado == tend.SUBINDO
    assert r.n_observacoes == 29
    assert tend.tendencia_valor(df.assign(valor=np.nan)).estado == tend.INSUFICIENTE


def test_valor_nao_positivo_nao_quebra_o_log():
    df = _serie_valor(efeito=0.6)
    df.loc[df.index[0], "valor"] = 0.0
    df.loc[df.index[1], "valor"] = -3.0
    r = tend.tendencia_valor(df)
    assert r.n_observacoes == len(df) - 2
    assert r.estado in tend.ESTADOS


def test_mudanca_de_mix_de_formato_sem_efeito_real_nao_gera_seta_com_controle():
    rng = np.random.default_rng(11)
    n = 120
    t = np.linspace(0, 1, n)
    formato = (rng.random(n) < 0.1 + 0.8 * t).astype(int)  # mix muda no tempo
    y = 100 * np.exp(1.1 * formato + rng.normal(0, 0.3, n))  # sem efeito do tempo
    df = pd.DataFrame({"data": _datas(n, 1), "valor": y, "formato": formato})
    sem_controle = tend.tendencia_valor(df)
    com_controle = tend.tendencia_valor(df, coluna_formato="formato")
    assert sem_controle.estado == tend.SUBINDO  # o mix engana o OLS simples
    assert com_controle.estado == tend.ESTAVEL


def test_proporcao_tendencia_clara_plana_e_curta():
    sobe = tend.tendencia_proporcao(_serie_prop(efeito=1.0, total=200))
    assert sobe.estado == tend.SUBINDO and sobe.variacao > 0.3
    plana = tend.tendencia_proporcao(_serie_prop(efeito=0.0, seed=0))
    assert plana.estado == tend.ESTAVEL
    curta = tend.tendencia_proporcao(_serie_prop(n=4, efeito=1.0))
    assert curta.estado == tend.INSUFICIENTE


def test_proporcao_mix_sem_efeito_real_com_controle():
    rng = np.random.default_rng(2)
    n = 120
    t = np.linspace(0, 1, n)
    formato = (rng.random(n) < 0.1 + 0.8 * t).astype(int)
    tot = rng.integers(20, 80, n)
    p = np.clip(0.2 * np.exp(0.9 * formato), 0, 0.95)
    df = pd.DataFrame(
        {
            "data": _datas(n, 1),
            "positivos": rng.binomial(tot, p),
            "total": tot,
            "formato": formato,
        }
    )
    assert tend.tendencia_proporcao(df, coluna_formato="formato").estado == tend.ESTAVEL


def test_proporcao_vazia_nulos_e_invalidos():
    assert tend.tendencia_proporcao(pd.DataFrame()).estado == tend.INSUFICIENTE
    df = _serie_prop(efeito=1.0, total=200)
    df.loc[df.index[0], "total"] = 0  # sem comentarios: descartado
    df.loc[df.index[1], "positivos"] = np.nan
    df.loc[df.index[2], "positivos"] = df.loc[df.index[2], "total"] + 5  # k > n
    r = tend.tendencia_proporcao(df)
    assert r.n_observacoes == len(df) - 3


def test_conjunto_e_mediana_das_tendencias_com_peso_igual_por_perfil():
    perfis = [tend.tendencia_valor(_serie_valor(efeito=0.5, seed=s)) for s in range(7)]
    conj = tend.tendencia_conjunto(perfis)
    assert conj.estado == tend.SUBINDO
    assert conj.n_perfis == 7
    # um perfil dominante (muito mais dados) com tendencia oposta nao decide sozinho
    dominante = tend.tendencia_valor(_serie_valor(n=400, efeito=-0.6, seed=99))
    assert tend.tendencia_conjunto([*perfis, dominante]).estado == tend.SUBINDO


def test_conjunto_poucos_perfis_ou_insuficientes_e_deterministico():
    insuf = tend.tendencia_valor(_serie_valor(n=3))
    assert tend.tendencia_conjunto([]).estado == tend.INSUFICIENTE
    assert tend.tendencia_conjunto([insuf] * 10).estado == tend.INSUFICIENTE
    ok = [tend.tendencia_valor(_serie_valor(efeito=0.5, seed=s)) for s in range(3)]
    assert tend.tendencia_conjunto(ok).estado == tend.INSUFICIENTE  # < minimo
    grande = [tend.tendencia_valor(_serie_valor(efeito=0.5, seed=s)) for s in range(8)]
    assert tend.tendencia_conjunto(grande) == tend.tendencia_conjunto(grande)


def test_tendencia_de_um_perfil_nao_depende_dos_outros():
    a = _serie_valor(efeito=0.5, seed=1)
    sozinho = tend.tendencia_valor(a)
    _outros = [_serie_valor(efeito=-0.9, seed=s) for s in range(5)]
    assert tend.tendencia_valor(a) == sozinho
