"""Testes do Escore composto / Scorecard (ADR 0030 / ADR 0047, issue #184).

Seams: `min_max_normalize`, `estimar_tendencia_engajamento`,
`classificar_tendencia` (funcoes puras) e `GovernorScorecardScorer.score`
(DataFrames sinteticos pequenos, mesmo padrao de `tests/test_nsm_scorer.py`)."""

import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from deltalake import DeltaTable

from src.delta_io import conform_to_schema
from src.modeling.governor_scorecard import (
    DIMENSOES,
    ESTADOS_TENDENCIA,
    MIN_DIAS_DISTINTOS,
    MIN_EFEITO_MENSAL,
    MIN_PUBLICACOES,
    TENDENCIA_CAINDO,
    TENDENCIA_DADOS_INSUFICIENTES,
    TENDENCIA_ESTAVEL,
    TENDENCIA_SUBINDO,
    GovernorScorecardScorer,
    classificar_tendencia,
    estimar_tendencia_engajamento,
    min_max_normalize,
    normalize_input_url,
    preparar_publicacoes,
)
from src.schemas_delta import GOLD_GOVERNOR_SCORECARD_SCHEMA

NOW = pd.Timestamp("2026-11-01")
INICIO = pd.Timestamp("2026-08-16")  # inicio da Coleta do TCC (70 dias)

COLUNAS_PUB = ["id", "inputUrl", "likesCount", "commentsCount", "data_hora"]


def _publicacoes(
    inputUrl: str,
    taxa_mensal: float,
    n: int = 40,
    dias: int = 60,
    ruido: float = 0.05,
    nivel: float = 1000.0,
    seed: int = 7,
    prefixo: str = "p",
    tipo: str | None = None,
) -> list[dict]:
    """`n` publicacoes de um perfil espalhadas por `dias` dias a partir de
    INICIO, com engajamento log-linear de `taxa_mensal` ao mes e ruido
    log-normal deterministico (`seed`)."""
    rng = np.random.default_rng(seed)
    offsets = np.linspace(0, dias, n)
    rows = []
    for i, d in enumerate(offsets):
        log_y = (
            math.log(nivel) + math.log1p(taxa_mensal) * d / 30 + rng.normal(0, ruido)
        )
        row = {
            "id": f"{prefixo}-{inputUrl}-{i}",
            "inputUrl": inputUrl,
            "likesCount": round(math.exp(log_y)),
            "commentsCount": 0,
            "data_hora": INICIO + pd.Timedelta(hours=float(d) * 24),
        }
        if tipo is not None:
            row["Tipo"] = tipo
        rows.append(row)
    return rows


class TestMinMax:
    def test_valores_ficam_entre_0_e_100(self):
        out = min_max_normalize(pd.Series([10.0, 20.0, 30.0]))
        assert out.tolist() == [0.0, 50.0, 100.0]

    def test_amplitude_zero_nao_divide_por_zero_e_vira_50(self):
        out = min_max_normalize(pd.Series([7.0, 7.0, 7.0]))
        assert out.tolist() == [50.0, 50.0, 50.0]

    def test_nulos_ficam_fora_do_min_max_e_continuam_nulos(self):
        out = min_max_normalize(pd.Series([10.0, None, 30.0]))
        assert out.iloc[0] == 0.0 and out.iloc[2] == 100.0
        assert math.isnan(out.iloc[1])


class TestClassificarTendencia:
    def test_nao_confiavel_e_dados_insuficientes(self):
        assert classificar_tendencia(0.5, 0.4, 0.6, False) == (
            TENDENCIA_DADOS_INSUFICIENTES
        )
        assert (
            classificar_tendencia(float("nan"), float("nan"), float("nan"), True)
            == TENDENCIA_DADOS_INSUFICIENTES
        )

    def test_subindo_exige_ic_acima_de_zero_e_efeito_minimo(self):
        assert classificar_tendencia(0.10, 0.02, 0.18, True) == TENDENCIA_SUBINDO
        # IC acima de zero, mas efeito abaixo de MIN_EFEITO_MENSAL -> Estavel
        assert (
            classificar_tendencia(MIN_EFEITO_MENSAL - 0.01, 0.01, 0.07, True)
            == TENDENCIA_ESTAVEL
        )
        # efeito grande, mas IC cruza o zero -> Estavel
        assert classificar_tendencia(0.10, -0.02, 0.22, True) == TENDENCIA_ESTAVEL

    def test_caindo_e_simetrico(self):
        assert classificar_tendencia(-0.10, -0.18, -0.02, True) == TENDENCIA_CAINDO
        assert classificar_tendencia(-0.03, -0.07, -0.01, True) == TENDENCIA_ESTAVEL

    def test_rotulos_sao_os_do_context(self):
        assert ESTADOS_TENDENCIA == (
            "Subindo",
            "Caindo",
            "Estável",
            "Dados insuficientes",
        )


class TestEstimarTendenciaEngajamento:
    def test_alta_clara_e_subindo_e_recupera_a_taxa(self):
        res = estimar_tendencia_engajamento(pd.DataFrame(_publicacoes("a", 0.30)), NOW)
        assert res["confiavel"] is True
        assert res["estado"] == TENDENCIA_SUBINDO
        assert res["taxa_mensal"] == pytest.approx(0.30, abs=0.03)
        assert res["ic_inferior"] < res["taxa_mensal"] < res["ic_superior"]
        assert res["ic_inferior"] > 0
        assert res["n_publicacoes"] == 40
        assert res["n_dias"] >= MIN_DIAS_DISTINTOS

    def test_queda_clara_e_caindo(self):
        res = estimar_tendencia_engajamento(pd.DataFrame(_publicacoes("a", -0.30)), NOW)
        assert res["estado"] == TENDENCIA_CAINDO
        assert res["taxa_mensal"] == pytest.approx(-0.30, abs=0.03)
        assert res["ic_superior"] < 0

    def test_sem_variacao_e_estavel_com_ic_cruzando_zero(self):
        res = estimar_tendencia_engajamento(
            pd.DataFrame(_publicacoes("a", 0.0, ruido=0.3)), NOW
        )
        assert res["confiavel"] is True
        assert res["estado"] == TENDENCIA_ESTAVEL
        assert res["ic_inferior"] < 0 < res["ic_superior"]

    def test_poucas_publicacoes_fica_pendente_e_dados_insuficientes(self):
        res = estimar_tendencia_engajamento(
            pd.DataFrame(_publicacoes("a", 0.30, n=MIN_PUBLICACOES - 1)), NOW
        )
        assert res["confiavel"] is False
        assert res["estado"] == TENDENCIA_DADOS_INSUFICIENTES
        assert math.isnan(res["taxa_mensal"])
        assert math.isnan(res["ic_inferior"]) and math.isnan(res["ic_superior"])
        assert res["n_publicacoes"] == MIN_PUBLICACOES - 1

    def test_poucos_dias_distintos_fica_pendente(self):
        # 40 publicacoes concentradas em 5 dias
        rows = _publicacoes("a", 0.30, n=40, dias=4)
        res = estimar_tendencia_engajamento(pd.DataFrame(rows), NOW)
        assert res["n_publicacoes"] == 40
        assert res["n_dias"] < MIN_DIAS_DISTINTOS
        assert res["confiavel"] is False
        assert res["estado"] == TENDENCIA_DADOS_INSUFICIENTES

    def test_limiar_exato_de_publicacoes_e_dias_e_confiavel(self):
        rows = _publicacoes("a", 0.30, n=MIN_PUBLICACOES, dias=MIN_DIAS_DISTINTOS - 1)
        res = estimar_tendencia_engajamento(pd.DataFrame(rows), NOW)
        assert (res["n_publicacoes"], res["n_dias"]) == (
            MIN_PUBLICACOES,
            MIN_DIAS_DISTINTOS,
        )
        assert res["confiavel"] is True

    def test_publicacoes_com_menos_de_7_dias_sao_excluidas(self):
        rows = _publicacoes("a", 0.30)
        ultima = rows[-1]["data_hora"]
        # now 3 dias depois da ultima: as publicacoes dos ultimos 7 dias caem
        cedo = estimar_tendencia_engajamento(
            pd.DataFrame(rows), ultima + pd.Timedelta(days=3)
        )
        tarde = estimar_tendencia_engajamento(
            pd.DataFrame(rows), ultima + pd.Timedelta(days=30)
        )
        assert cedo["n_publicacoes"] < tarde["n_publicacoes"] == 40

    def test_dedup_reel_post_por_id_prefere_a_linha_de_reel(self):
        reels = pd.DataFrame(_publicacoes("a", 0.30, tipo="REELS"))
        # Mesmos ids capturados pelo scraper de posts, com contagens defasadas
        # (menores): se a linha de post vencesse, a taxa mudaria.
        posts = reels.assign(
            likesCount=(reels["likesCount"] * 0.5).round(), Tipo="FEED"
        )
        so_reels = estimar_tendencia_engajamento(reels, NOW)
        com_dups = estimar_tendencia_engajamento(pd.concat([posts, reels]), NOW)
        assert com_dups["n_publicacoes"] == 40
        assert com_dups["taxa_mensal"] == pytest.approx(so_reels["taxa_mensal"])
        pub = preparar_publicacoes(pd.concat([posts, reels]), NOW)
        assert (pub["formato"] == 1).all()

    def test_publicacoes_fixadas_ficam_fora(self):
        rows = _publicacoes("a", 0.0, ruido=0.0)
        base = estimar_tendencia_engajamento(pd.DataFrame(rows), NOW)
        fixada = {
            "id": "fixada",
            "inputUrl": "a",
            "likesCount": 10_000_000,
            "commentsCount": 0,
            "data_hora": pd.Timestamp("2022-01-01"),
            "isPinned": True,
        }
        com_fixada = estimar_tendencia_engajamento(pd.DataFrame([*rows, fixada]), NOW)
        assert com_fixada["n_publicacoes"] == base["n_publicacoes"] == 40
        assert com_fixada["taxa_mensal"] == pytest.approx(base["taxa_mensal"])
        # Sem a marcacao, a mesma linha (antiga e gigante) entraria e distorceria
        sem_marcacao = estimar_tendencia_engajamento(
            pd.DataFrame([*rows, {**fixada, "isPinned": None}]), NOW
        )
        assert sem_marcacao["n_publicacoes"] == 41
        assert sem_marcacao["taxa_mensal"] != pytest.approx(base["taxa_mensal"])

    def test_controle_de_formato_so_com_dois_formatos(self):
        # Reels no nivel 4000 e posts no nivel 1000, ambos SEM variacao real;
        # o mix muda (reels no inicio, posts no fim): sem controle, a reta
        # desceria; com o controle de formato, fica Estavel.
        reels = _publicacoes(
            "a", 0.0, n=25, dias=35, nivel=4000, tipo="REELS", prefixo="r"
        )
        posts = _publicacoes("a", 0.0, n=25, dias=35, nivel=1000, tipo="FEED")
        for row in posts:
            row["data_hora"] = row["data_hora"] + pd.Timedelta(days=25)
        res = estimar_tendencia_engajamento(pd.DataFrame(reels + posts), NOW)
        assert res["estado"] == TENDENCIA_ESTAVEL
        assert abs(res["taxa_mensal"]) < 0.10

        # So um formato: o resultado e a regressao simples de log(y) em t
        so_posts = pd.DataFrame(_publicacoes("a", 0.20, tipo="FEED"))
        res1 = estimar_tendencia_engajamento(so_posts, NOW)
        pub = preparar_publicacoes(so_posts, NOW)
        t = (pub["data_hora"] - pub["data_hora"].min()).dt.total_seconds() / 86400 / 30
        beta = np.polyfit(t, np.log(pub["engajamento"]), 1)[0]
        assert res1["taxa_mensal"] == pytest.approx(math.expm1(beta))

    def test_formato_pode_vir_pronto_na_coluna_formato(self):
        df = pd.DataFrame(_publicacoes("a", 0.0, ruido=0.0))
        df["formato"] = [1 if i % 2 else 0 for i in range(len(df))]
        pub = preparar_publicacoes(df, NOW)
        assert pub["formato"].sum() == 20

    def test_engajamento_zero_nao_quebra_o_log(self):
        rows = _publicacoes("a", 0.0)
        for row in rows:
            row["likesCount"] = 0
        res = estimar_tendencia_engajamento(pd.DataFrame(rows), NOW)
        assert res["confiavel"] is True
        assert res["taxa_mensal"] == pytest.approx(0.0)

    def test_sem_publicacoes_nao_levanta_erro(self):
        vazio = pd.DataFrame(columns=COLUNAS_PUB)
        res = estimar_tendencia_engajamento(vazio, NOW)
        assert res["estado"] == TENDENCIA_DADOS_INSUFICIENTES
        assert (res["n_publicacoes"], res["n_dias"]) == (0, 0)
        assert estimar_tendencia_engajamento(None, NOW)["confiavel"] is False

    def test_data_hora_com_timezone_e_now_com_timezone(self):
        df = pd.DataFrame(_publicacoes("a", 0.30))
        df["data_hora"] = df["data_hora"].dt.tz_localize("UTC")
        a = estimar_tendencia_engajamento(df, NOW)
        b = estimar_tendencia_engajamento(df, NOW.tz_localize("UTC"))
        assert a["estado"] == b["estado"] == TENDENCIA_SUBINDO
        assert a["taxa_mensal"] == pytest.approx(b["taxa_mensal"])


def _perfil(url: str, username: str, followers: int = 1000) -> dict:
    return {"inputUrl": url, "username": username, "followersCount": followers}


def _reel(url: str, i: int, plays: int | None, likes: int, comments: int) -> dict:
    return {
        "id": f"r-{url}-{i}",
        "inputUrl": url,
        "videoPlayCount": plays,
        "likesCount": likes,
        "commentsCount": comments,
        "data_hora": pd.Timestamp("2024-01-10"),
        "isPinned": True,  # fixado: fora da Consistencia, dentro das outras dimensoes
    }


def _coment(url: str, label: str, fonte: str = "comentario") -> dict:
    return {"inputUrl": url, "fonte": fonte, "sentiment_label": label}


def _cenario(n_perfis: int = 5):
    """n perfis com desempenho crescente (gov0 pior, ultimo melhor), todos com
    publicacoes suficientes e taxa mensal +10%."""
    perfis, reels, posts, sent = [], [], [], []
    for k in range(n_perfis):
        url = f"https://www.instagram.com/gov{k}/"
        perfis.append(_perfil(url, f"gov{k}", followers=1000))
        for i in range(2):
            reels.append(
                _reel(
                    url,
                    i,
                    plays=1000 * (k + 1),
                    likes=50 * (k + 1),
                    comments=5 * (k + 1),
                )
            )
        sent += [_coment(url, "positive")] * (k + 1) + [_coment(url, "negative")] * (
            n_perfis - k
        )
        posts += _publicacoes(url, 0.10, seed=k)
    return (
        pd.DataFrame(perfis),
        pd.DataFrame(reels),
        pd.DataFrame(posts),
        pd.DataFrame(sent),
    )


def _score(perfis, reels, posts, sent):
    return GovernorScorecardScorer().score(perfis, reels, posts, sent, now=NOW)


class TestScorer:
    def test_dimensoes_brutas_seguem_as_formulas(self):
        perfis, reels, posts, sent = _cenario(3)
        out = _score(perfis, reels, posts, sent).set_index("username")
        g1 = out.loc["gov1"]
        assert g1["alcance"] == pytest.approx(2000)
        assert g1["ativacao"] == pytest.approx(100 / 1000)
        assert g1["profundidade"] == pytest.approx(10 / 2000)
        # gov1 (n=3): 2 positivos, 2 negativos -> 2/4
        assert g1["qualidade"] == pytest.approx(2 / 4)
        assert g1["consistencia"] == pytest.approx(0.10, abs=0.03)
        assert g1["consistencia"] == g1["consistencia_taxa_mensal"]
        assert g1["consistencia_ic_inferior"] < g1["consistencia"]
        assert g1["consistencia"] < g1["consistencia_ic_superior"]
        assert g1["consistencia_n_publicacoes"] == 40
        assert g1["consistencia_n_dias"] >= MIN_DIAS_DISTINTOS
        assert g1["tendencia_engajamento"] == TENDENCIA_SUBINDO

    def test_colunas_de_saida_sao_as_do_contrato(self):
        perfis, reels, posts, sent = _cenario(2)
        out = _score(perfis, reels, posts, sent)
        esperadas = [
            f.name
            for f in GOLD_GOVERNOR_SCORECARD_SCHEMA
            if f.name not in ("_run_id", "_generated_at")
        ]
        assert out.columns.tolist() == esperadas
        assert "consistencia_n_meses" not in out.columns
        assert not any(c.startswith("cmgr_") for c in out.columns)
        assert set(out["tendencia_engajamento"]) <= set(ESTADOS_TENDENCIA)

    def test_normalizadas_entre_0_e_100_e_escore_e_media_com_pesos_iguais(self):
        perfis, reels, posts, sent = _cenario(5)
        out = _score(perfis, reels, posts, sent)
        for dim in DIMENSOES:
            assert out[f"{dim}_norm"].dropna().between(0, 100).all()
        linha = out.iloc[0]
        esperado = sum(linha[f"{d}_norm"] for d in DIMENSOES) / 5
        assert linha["escore"] == pytest.approx(esperado)
        assert (out["n_dimensoes"] == 5).all()

    def test_consistencia_normalizada_ordena_pela_taxa_mensal(self):
        perfis, reels, posts, sent = _cenario(3)
        posts = pd.DataFrame(
            _publicacoes(perfis.iloc[0]["inputUrl"], -0.20, seed=0)
            + _publicacoes(perfis.iloc[1]["inputUrl"], 0.0, seed=1)
            + _publicacoes(perfis.iloc[2]["inputUrl"], 0.30, seed=2)
        )
        out = _score(perfis, reels, posts, sent).set_index("username")
        assert out.loc["gov0", "consistencia_norm"] == 0.0
        assert out.loc["gov2", "consistencia_norm"] == 100.0
        assert out.loc["gov0", "tendencia_engajamento"] == TENDENCIA_CAINDO
        assert out.loc["gov2", "tendencia_engajamento"] == TENDENCIA_SUBINDO

    def test_ranking_deterministico_com_desempate_estavel_por_inputUrl(self):
        perfis, reels, posts, sent = _cenario(3)
        url0 = perfis.iloc[0]["inputUrl"]
        novo = "https://www.instagram.com/aaa/"
        perfis2 = pd.concat(
            [perfis, perfis.iloc[[0]].assign(inputUrl=novo, username="aaa")],
            ignore_index=True,
        )

        def clone(df):
            c = df[df["inputUrl"] == url0]
            return c.assign(inputUrl=novo, id=c["id"] + "-clone")

        reels2 = pd.concat([reels, clone(reels)])
        posts2 = pd.concat([posts, clone(posts)])
        sent2 = pd.concat([sent, sent[sent["inputUrl"] == url0].assign(inputUrl=novo)])
        a = _score(perfis2, reels2, posts2, sent2)
        b = _score(perfis2.iloc[::-1], reels2, posts2, sent2.iloc[::-1])
        assert a["ranking"].tolist() == [1, 2, 3, 4]
        assert a[["inputUrl", "ranking"]].equals(b[["inputUrl", "ranking"]])
        pos = a.set_index("username")["ranking"]
        assert pos["gov2"] == 1
        assert pos["aaa"] < pos["gov0"]  # empate de escore -> inputUrl menor primeiro

    def test_amplitude_zero_em_todas_as_dimensoes_nao_quebra(self):
        perfis, reels, posts, sent = _cenario(1)
        out = _score(perfis, reels, posts, sent)
        assert out.iloc[0]["escore"] == pytest.approx(50.0)

    def test_consistencia_pendente_renormaliza_pesos_para_025(self):
        perfis, reels, posts, sent = _cenario(4)
        url0 = perfis.iloc[0]["inputUrl"]
        # gov0 fica com poucas publicacoes (abaixo de MIN_PUBLICACOES)
        posts = pd.concat(
            [
                posts[posts["inputUrl"] != url0],
                posts[posts["inputUrl"] == url0].head(MIN_PUBLICACOES - 1),
            ]
        )
        out = _score(perfis, reels, posts, sent).set_index("username")
        g0 = out.loc["gov0"]
        assert bool(g0["consistencia_pendente"]) is True
        assert math.isnan(g0["consistencia"]) and math.isnan(g0["consistencia_norm"])
        assert math.isnan(g0["consistencia_taxa_mensal"])
        assert g0["consistencia_n_publicacoes"] == MIN_PUBLICACOES - 1
        assert g0["tendencia_engajamento"] == TENDENCIA_DADOS_INSUFICIENTES
        assert g0["n_dimensoes"] == 4
        quatro = ["alcance", "ativacao", "qualidade", "profundidade"]
        assert g0["escore"] == pytest.approx(
            sum(g0[f"{d}_norm"] for d in quatro) * 0.25
        )
        assert bool(out.loc["gov1", "consistencia_pendente"]) is False
        assert out["escore"].notna().all()

    def test_perfil_sem_dados_nao_levanta_excecao_e_fica_sem_escore(self):
        perfis, reels, posts, sent = _cenario(3)
        extra = pd.DataFrame(
            [_perfil("https://www.instagram.com/vazio/", "vazio", followers=0)]
        )
        perfis = pd.concat([perfis, extra], ignore_index=True)
        out = _score(perfis, reels, posts, sent).set_index("username")
        v = out.loc["vazio"]
        for dim in DIMENSOES:
            assert math.isnan(v[dim])
        assert v["n_dimensoes"] == 0
        assert math.isnan(v["escore"])
        assert pd.isna(v["ranking"])
        assert v["tendencia_engajamento"] == TENDENCIA_DADOS_INSUFICIENTES
        assert (v["consistencia_n_publicacoes"], v["consistencia_n_dias"]) == (0, 0)
        assert out.loc[["gov0", "gov1", "gov2"], "ranking"].tolist() == [3, 2, 1]

    def test_plays_zero_gera_alcance_zero_e_profundidade_nula(self):
        perfis, reels, posts, sent = _cenario(3)
        reels.loc[reels["inputUrl"] == perfis.iloc[0]["inputUrl"], "videoPlayCount"] = 0
        out = _score(perfis, reels, posts, sent).set_index("username")
        assert out.loc["gov0", "alcance"] == 0
        assert math.isnan(out.loc["gov0", "profundidade"])

    def test_legenda_e_transcricao_nao_contam_em_qualidade(self):
        perfis, reels, posts, sent = _cenario(3)
        url = perfis.iloc[0]["inputUrl"]
        ruido = pd.DataFrame([_coment(url, "negative", fonte="legenda")] * 50)
        out = _score(perfis, reels, posts, pd.concat([sent, ruido])).set_index(
            "username"
        )
        assert out.loc["gov0", "qualidade"] == pytest.approx(1 / 4)

    def test_join_por_inputUrl_normalizado(self):
        assert normalize_input_url(
            "HTTPS://www.Instagram.com/Gov/ "
        ) == normalize_input_url("https://www.instagram.com/gov")
        perfis, reels, posts, sent = _cenario(3)
        reels["inputUrl"] = reels["inputUrl"].str.rstrip("/").str.upper()
        out = _score(perfis, reels, posts, sent).set_index("username")
        assert out.loc["gov1", "alcance"] == pytest.approx(2000)

    def test_post_repetido_entre_posts_e_reels_conta_uma_vez(self):
        perfis, reels, posts, sent = _cenario(3)
        # 10 primeiras publicacoes de cada perfil sao reels (Tipo == REELS no
        # scraper de posts) e tambem chegam pelo scraper de reels: cada uma
        # conta uma vez so, por mais vezes que apareca.
        posts = posts.assign(
            Tipo=np.where(posts.groupby("inputUrl").cumcount() < 10, "REELS", "FEED")
        )
        como_reels = (
            posts[posts["Tipo"] == "REELS"]
            .drop(columns="Tipo")
            .assign(videoPlayCount=None, isPinned=None)
        )
        antes = _score(perfis, pd.concat([reels, como_reels]), posts, sent)
        depois = _score(
            perfis,
            pd.concat([reels, como_reels]),
            pd.concat([posts, posts[posts["Tipo"] == "REELS"]]),  # repete de novo
            sent,
        ).set_index("username")
        antes = antes.set_index("username")
        assert (depois["consistencia_n_publicacoes"] == 40).all()
        for user in ("gov0", "gov1", "gov2"):
            assert depois.loc[user, "consistencia"] == pytest.approx(
                antes.loc[user, "consistencia"]
            )
        # ...e a estimativa e a mesma de quando os reels so chegam pelo
        # scraper de posts (dedup nao muda o formato nem o engajamento).
        so_posts = _score(perfis, reels, posts, sent).set_index("username")
        for user in ("gov0", "gov1", "gov2"):
            assert so_posts.loc[user, "consistencia"] == pytest.approx(
                antes.loc[user, "consistencia"]
            )

    def test_reel_fixado_na_silver_fica_fora_da_consistencia(self):
        perfis, reels, posts, sent = _cenario(2)
        url0 = perfis.iloc[0]["inputUrl"]
        antes = _score(perfis, reels, posts, sent).set_index("username")
        fixado = pd.DataFrame(
            [
                {
                    **_reel(url0, 99, plays=None, likes=5_000_000, comments=0),
                    "data_hora": pd.Timestamp("2021-05-05"),
                    "isPinned": True,
                }
            ]
        )
        depois = _score(perfis, pd.concat([reels, fixado]), posts, sent).set_index(
            "username"
        )
        assert depois.loc["gov0", "consistencia_n_publicacoes"] == 40
        assert depois.loc["gov0", "consistencia"] == pytest.approx(
            antes.loc["gov0", "consistencia"]
        )


class TestRobustez:
    def test_data_hora_com_timezone_e_ids_nulos_nao_quebram(self):
        perfis, reels, posts, sent = _cenario(3)
        posts = posts.assign(
            data_hora=pd.to_datetime(posts["data_hora"]).dt.tz_localize("UTC")
        )
        posts.loc[posts.index[:4], "id"] = None
        out = _score(perfis, reels, posts, sent)
        assert out["escore"].notna().all()

    def test_posts_sem_colunas_opcionais_da_silver(self):
        perfis, reels, posts, sent = _cenario(2)
        reels = reels.drop(columns=["isPinned"])
        assert set(posts.columns) == set(COLUNAS_PUB)  # sem isPinned nem Tipo
        out = _score(perfis, reels, posts, sent)
        assert (out["tendencia_engajamento"] == TENDENCIA_SUBINDO).all()


class TestWrite:
    def test_grava_no_schema_declarado(self, tmp_path):
        perfis, reels, posts, sent = _cenario(5)
        out = _score(perfis, reels, posts, sent)
        path = tmp_path / "governor_scorecard"
        GovernorScorecardScorer().write(
            out, path, "run-1", generated_at=datetime(2026, 11, 1, tzinfo=timezone.utc)
        )
        lido = DeltaTable(str(path)).to_pandas()
        assert len(lido) == 5
        assert set(lido["_run_id"]) == {"run-1"}
        assert lido["escore"].notna().all()
        assert set(lido["tendencia_engajamento"]) == {TENDENCIA_SUBINDO}
        assert lido["consistencia_n_publicacoes"].dtype == "int64"

    def test_grava_perfil_pendente_com_nulos_e_estado(self, tmp_path):
        perfis, reels, posts, sent = _cenario(2)
        posts = posts[posts["inputUrl"] != perfis.iloc[0]["inputUrl"]]
        out = _score(perfis, reels, posts, sent)
        path = tmp_path / "governor_scorecard"
        GovernorScorecardScorer().write(out, path, "run-2")
        lido = DeltaTable(str(path)).to_pandas().set_index("username")
        assert lido.loc["gov0", "tendencia_engajamento"] == (
            TENDENCIA_DADOS_INSUFICIENTES
        )
        assert pd.isna(lido.loc["gov0", "consistencia_taxa_mensal"])
        assert lido.loc["gov0", "consistencia_n_publicacoes"] == 0

    def test_schema_exige_inputUrl_nao_nulo(self):
        perfis, reels, posts, sent = _cenario(2)
        out = _score(perfis, reels, posts, sent)
        out["_run_id"] = "r"
        out["_generated_at"] = datetime(2026, 11, 1, tzinfo=timezone.utc)
        out.loc[0, "inputUrl"] = None
        with pytest.raises(ValueError, match="non-nullable"):
            conform_to_schema(out, GOLD_GOVERNOR_SCORECARD_SCHEMA)
