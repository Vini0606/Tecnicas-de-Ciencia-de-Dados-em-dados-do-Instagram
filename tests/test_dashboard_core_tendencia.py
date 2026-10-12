"""Testes do nucleo da Tendencia (ADR 0040 / issue #285) -- funcoes puras com
DataFrames. Metodo e limiares PROVISORIOS (aguardam o backtest #284)."""

import inspect

import numpy as np
import pandas as pd
import pytest

from dashboard.core import tendencia as tend


def _datas(n, passo=2):
    base = pd.Timestamp("2026-01-01")
    return [base + pd.Timedelta(days=passo * i) for i in range(n)]


def _serie_valor(n=40, efeito=0.0, ruido=0.1, seed=0):
    """Valor com tendencia log-linear de `efeito` (fracao POR 90 DIAS)."""
    rng = np.random.default_rng(seed)
    t = 2 * np.arange(n) / tend.PERIODO_DIAS  # em periodos de 90 dias
    y = 100 * np.exp(np.log1p(efeito) * t + rng.normal(0, ruido, n))
    return pd.DataFrame({"data": _datas(n), "valor": y})


def _serie_prop(n=40, efeito=0.0, seed=0, total=60):
    rng = np.random.default_rng(seed)
    t = 2 * np.arange(n) / tend.PERIODO_DIAS
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


# --- variacao por periodo de 90 dias (independe do tamanho da janela) --------


def _serie_exata(dias_totais, efeito=0.3, passo=3):
    dias = np.arange(0, dias_totais, passo)
    y = 100 * np.exp(np.log1p(efeito) * dias / tend.PERIODO_DIAS)
    base = pd.Timestamp("2026-01-01")
    return pd.DataFrame(
        {"data": [base + pd.Timedelta(days=int(d)) for d in dias], "valor": y}
    )


@pytest.mark.parametrize("janela", [45, 90, 180, 720])
def test_variacao_e_por_90_dias_e_nao_depende_da_janela(janela):
    r = tend.tendencia_valor(_serie_exata(janela))
    assert r.variacao == pytest.approx(0.3, abs=1e-6)


def test_variacao_por_90_dias_em_proporcao_independe_da_janela():
    def serie(janela):
        dias = np.arange(0, janela, 3)
        p = 0.3 * np.exp(np.log(1.2) * dias / tend.PERIODO_DIAS)
        tot = np.full(len(dias), 1000)
        base = pd.Timestamp("2026-01-01")
        return pd.DataFrame(
            {
                "data": [base + pd.Timedelta(days=int(d)) for d in dias],
                "positivos": p * tot,
                "total": tot,
            }
        )

    curta = tend.tendencia_proporcao(serie(120))
    longa = tend.tendencia_proporcao(serie(600))
    assert curta.variacao == pytest.approx(longa.variacao, abs=1e-3)
    assert curta.variacao == pytest.approx(0.2, abs=0.01)


# --- bordas dos limiares, lendo as constantes ---------------------------------


def _valor_n_dias(n, n_dias, efeito=1.0, seed=0):
    """`n` linhas em exatamente `n_dias` dias distintos (dias consecutivos)."""
    rng = np.random.default_rng(seed)
    dias = np.arange(n) % n_dias
    t = dias / tend.PERIODO_DIAS
    y = 100 * np.exp(np.log1p(efeito) * t + rng.normal(0, 0.05, n))
    base = pd.Timestamp("2026-01-01")
    return pd.DataFrame(
        {"data": [base + pd.Timedelta(days=int(d)) for d in dias], "valor": y}
    )


def test_borda_minimo_de_observacoes():
    assert tend.MIN_DIAS_DISTINTOS <= tend.MIN_OBSERVACOES  # premissa dos testes
    abaixo = tend.tendencia_valor(
        _valor_n_dias(tend.MIN_OBSERVACOES - 1, tend.MIN_DIAS_DISTINTOS)
    )
    assert abaixo.estado == tend.INSUFICIENTE
    assert abaixo.n_observacoes == tend.MIN_OBSERVACOES - 1
    no_minimo = tend.tendencia_valor(
        _valor_n_dias(tend.MIN_OBSERVACOES, tend.MIN_DIAS_DISTINTOS)
    )
    assert no_minimo.estado != tend.INSUFICIENTE
    assert no_minimo.n_observacoes == tend.MIN_OBSERVACOES


def test_borda_minimo_de_dias_distintos():
    n = tend.MIN_OBSERVACOES + 6
    abaixo = tend.tendencia_valor(_valor_n_dias(n, tend.MIN_DIAS_DISTINTOS - 1))
    assert abaixo.estado == tend.INSUFICIENTE
    assert abaixo.n_dias == tend.MIN_DIAS_DISTINTOS - 1
    no_minimo = tend.tendencia_valor(_valor_n_dias(n, tend.MIN_DIAS_DISTINTOS))
    assert no_minimo.estado != tend.INSUFICIENTE
    assert no_minimo.n_dias == tend.MIN_DIAS_DISTINTOS


def test_borda_minimo_de_perfis_no_conjunto():
    def perfis(k):
        return [
            tend.tendencia_valor(_serie_valor(efeito=0.5, seed=s)) for s in range(k)
        ]

    abaixo = tend.tendencia_conjunto(perfis(tend.MIN_PERFIS_CONJUNTO - 1))
    assert abaixo.estado == tend.INSUFICIENTE
    assert abaixo.n_perfis == tend.MIN_PERFIS_CONJUNTO - 1
    no_minimo = tend.tendencia_conjunto(perfis(tend.MIN_PERFIS_CONJUNTO))
    assert no_minimo.estado != tend.INSUFICIENTE
    assert no_minimo.n_perfis == tend.MIN_PERFIS_CONJUNTO


def test_borda_min_efeito_classificacao():
    # IC todo acima de zero: so vira Subindo se a estimativa passar de MIN_EFEITO
    ok = np.log1p(tend.MIN_EFEITO * 1.01)
    baixa = np.log1p(tend.MIN_EFEITO * 0.99)
    assert tend._classificar(ok, ok * 0.5, ok * 2) == tend.SUBINDO
    assert tend._classificar(baixa, baixa * 0.5, baixa * 2) == tend.ESTAVEL
    cai_ok = np.log1p(-tend.MIN_EFEITO * 1.01)
    cai_baixa = np.log1p(-tend.MIN_EFEITO * 0.99)
    assert tend._classificar(cai_ok, cai_ok * 2, cai_ok * 0.5) == tend.CAINDO
    assert tend._classificar(cai_baixa, cai_baixa * 2, cai_baixa * 0.5) == tend.ESTAVEL


# --- serie por data de PUBLICACAO ---------------------------------------------


def _pubs(ids, dias, base="2026-01-01"):
    d0 = pd.Timestamp(base)
    return pd.DataFrame(
        {
            "id": ids,
            "data_hora": [d0 + pd.Timedelta(days=int(x), hours=15) for x in dias],
        }
    )


def _coment(linhas):
    """linhas: (chave, id_reel, origem, label) -> DataFrame com id_comment unico."""
    return pd.DataFrame(
        [
            {
                "chave": c,
                "id_reel": i,
                "origem_comentario": o,
                "sentiment_label": lab,
                "id_comment": f"c{n}",
                "timestamp": "2030-01-01T00:00:00Z",
            }
            for n, (c, i, o, lab) in enumerate(linhas)
        ]
    )


def test_serie_junta_por_id_conforme_origem_e_usa_data_de_publicacao():
    # o MESMO id existe em reels e posts, com datas diferentes
    reels = _pubs(["x", "r2"], [0, 5])
    posts = _pubs(["x"], [9])
    com = _coment(
        [
            ("a", "x", "reel", "positive"),
            ("a", "x", "reel", "negative"),
            ("a", "x", "post", "positive"),
            ("a", "r2", "reel", "positive"),
        ]
    )
    r = tend.serie_positividade_por_publicacao(com, reels, posts)
    s = r.serie.set_index(["id_publicacao", "formato"])
    assert len(s) == 3
    assert s.loc[("x", "reel"), "data"] == pd.Timestamp("2026-01-01")  # sem hora
    assert s.loc[("x", "post"), "data"] == pd.Timestamp("2026-01-10")
    assert (s.loc[("x", "reel"), "positivos"], s.loc[("x", "reel"), "total"]) == (1, 2)
    assert r.taxa_correspondencia == 1.0 and r.n_correspondidos == 4


def test_serie_sem_correspondencia_fica_fora_e_nao_usa_data_do_comentario():
    reels = _pubs(["r1"], [0])
    com = _coment(
        [
            ("a", "r1", "reel", "positive"),
            ("a", "inexistente", "reel", "positive"),
            ("a", "r1", "story", "positive"),  # origem desconhecida
            ("a", None, "reel", "positive"),
        ]
    )
    r = tend.serie_positividade_por_publicacao(com, reels, pd.DataFrame())
    assert r.serie["total"].sum() == 1
    assert r.taxa_correspondencia == pytest.approx(0.25)
    assert r.n_comentarios == 4 and r.n_correspondidos == 1
    assert r.serie["data"].max() == pd.Timestamp("2026-01-01")  # nao 2030


def test_serie_ids_numericos_casam_com_texto_e_id_comment_repetido_conta_uma_vez():
    reels = pd.DataFrame(
        {"id": [123, 456], "data_hora": pd.to_datetime(["2026-02-01", "2026-02-02"])}
    )
    com = _coment([("a", "123", "reel", "positive"), ("a", "123", "reel", "positive")])
    com["id_comment"] = "igual"
    r = tend.serie_positividade_por_publicacao(com, reels, pd.DataFrame())
    assert r.n_comentarios == 1 and r.serie["total"].sum() == 1


def test_serie_vazia_ou_sem_colunas():
    for com in (pd.DataFrame(), pd.DataFrame({"x": [1]})):
        r = tend.serie_positividade_por_publicacao(com, pd.DataFrame(), pd.DataFrame())
        assert r.serie.empty and r.taxa_correspondencia is None
    com = _coment([("a", "r1", "reel", "positive")])
    r = tend.serie_positividade_por_publicacao(com, pd.DataFrame(), pd.DataFrame())
    assert r.serie.empty and r.taxa_correspondencia == 0.0


def test_minimos_contam_publicacoes_e_dias_de_publicacao_nao_linhas_por_formato():
    assert tend.MIN_DIAS_DISTINTOS <= tend.MIN_OBSERVACOES
    n_pub = tend.MIN_OBSERVACOES
    ids = [f"p{i}" for i in range(n_pub)]
    # varias publicacoes no mesmo dia e formato: agregar por (dia, formato) as fundiria
    dias = [i % tend.MIN_DIAS_DISTINTOS for i in range(n_pub)]
    reels = _pubs(ids, dias)
    linhas = []
    for i in ids:
        linhas += [("a", i, "reel", "positive")] * 3 + [
            ("a", i, "reel", "negative")
        ] * 2
    r = tend.serie_positividade_por_publicacao(_coment(linhas), reels, pd.DataFrame())
    assert len(r.serie) == n_pub  # uma linha por publicacao, nao por (dia, formato)
    t = tend.tendencia_positividade_comentarios(r.serie, "a")
    assert t.n_observacoes == n_pub and t.n_dias == tend.MIN_DIAS_DISTINTOS
    assert t.estado != tend.INSUFICIENTE
    # uma publicacao a menos -> abaixo do minimo
    menos = r.serie.iloc[:-1]
    assert (
        tend.tendencia_positividade_comentarios(menos, "a").estado == tend.INSUFICIENTE
    )
