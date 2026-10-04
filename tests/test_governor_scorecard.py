"""Testes do Escore composto / Scorecard (ADR 0030, issue #184).

Seams: `min_max_normalize` e `compute_cmgr_engajamento` (funcoes puras) e
`GovernorScorecardScorer.score` (DataFrames sinteticos pequenos, mesmo padrao
de `tests/test_nsm_scorer.py`)."""

import math
from datetime import datetime, timezone

import pandas as pd
import pytest
from deltalake import DeltaTable

from src.delta_io import conform_to_schema
from src.modeling.governor_scorecard import (
    DIMENSOES,
    GovernorScorecardScorer,
    compute_cmgr_engajamento,
    min_max_normalize,
    normalize_input_url,
)
from src.schemas_delta import GOLD_GOVERNOR_SCORECARD_SCHEMA

NOW = pd.Timestamp("2026-10-04")


def _posts_mensais(inputUrl: str, meses: dict[str, tuple[int, int]]) -> list[dict]:
    """`meses`: {"2026-03": (n_posts, engajamento_por_post)} -- publicados no dia 10."""
    rows = []
    for mes, (n, eng) in meses.items():
        for i in range(n):
            rows.append(
                {
                    "id": f"p-{inputUrl}-{mes}-{i}",
                    "inputUrl": inputUrl,
                    "likesCount": eng,
                    "commentsCount": 0,
                    "data_hora": pd.Timestamp(f"{mes}-10"),
                }
            )
    return rows


def _crescimento_10pct(inputUrl: str, n_meses: int = 6, n_posts: int = 3) -> list[dict]:
    """Ultimos `n_meses` meses completos antes de NOW (2026-09 para tras), +10% ao mes."""
    meses = {}
    for k in range(n_meses):
        mes = pd.Period("2026-09", "M") - (n_meses - 1 - k)
        meses[str(mes)] = (n_posts, round(1000 * 1.1**k))
    return _posts_mensais(inputUrl, meses)


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


class TestCmgrEngajamento:
    def test_recupera_taxa_de_crescimento_mensal(self):
        df = pd.DataFrame(_crescimento_10pct("a", n_meses=6))
        cmgr, n_meses = compute_cmgr_engajamento(df, NOW)
        assert n_meses == 6
        assert cmgr == pytest.approx(0.10, abs=0.01)

    def test_mes_corrente_e_excluido(self):
        rows = _crescimento_10pct("a", n_meses=4) + _posts_mensais(
            "a", {"2026-10": (5, 99999)}
        )
        # 'now' em 2026-10-20: os posts de outubro tem 10 dias (maduros), mas o mes e o corrente
        cmgr, n_meses = compute_cmgr_engajamento(
            pd.DataFrame(rows), pd.Timestamp("2026-10-20")
        )
        assert n_meses == 4
        assert cmgr == pytest.approx(0.10, abs=0.01)

    def test_mes_com_menos_de_3_posts_nao_conta(self):
        rows = _crescimento_10pct("a", n_meses=5)
        rows += _posts_mensais("a", {"2026-01": (2, 5000)})
        _, n_meses = compute_cmgr_engajamento(pd.DataFrame(rows), NOW)
        assert n_meses == 5

    def test_posts_com_menos_de_7_dias_sao_excluidos(self):
        base = _posts_mensais(
            "a", {f"2026-0{m}": (3, 1000 + 100 * m) for m in (4, 5, 6, 7)}
        )
        agosto = [
            {
                "id": f"ag{i}",
                "inputUrl": "a",
                "likesCount": 2000,
                "commentsCount": 0,
                "data_hora": pd.Timestamp("2026-08-30"),
            }
            for i in range(3)
        ]
        df = pd.DataFrame(base + agosto)
        # now = 2026-09-02: os posts de 08-30 tem 3 dias de vida -> excluidos, agosto vazio
        _, n_novos = compute_cmgr_engajamento(df, pd.Timestamp("2026-09-02"))
        # now = 2026-09-20: os mesmos posts tem 21 dias -> agosto vira um mes valido
        _, n_maduros = compute_cmgr_engajamento(df, pd.Timestamp("2026-09-20"))
        assert (n_novos, n_maduros) == (4, 5)

    def test_menos_de_4_meses_validos_fica_pendente(self):
        df = pd.DataFrame(_crescimento_10pct("a", n_meses=3))
        cmgr, n_meses = compute_cmgr_engajamento(df, NOW)
        assert math.isnan(cmgr)
        assert n_meses == 3

    def test_sem_posts_nao_levanta_erro(self):
        df = pd.DataFrame(
            columns=["id", "inputUrl", "likesCount", "commentsCount", "data_hora"]
        )
        cmgr, n_meses = compute_cmgr_engajamento(df, NOW)
        assert math.isnan(cmgr) and n_meses == 0

    def test_janela_limita_a_12_meses(self):
        df = pd.DataFrame(_crescimento_10pct("a", n_meses=15))
        _, n_meses = compute_cmgr_engajamento(df, NOW)
        assert n_meses == 12

    def test_engajamento_zero_nao_quebra_o_log(self):
        rows = _posts_mensais("a", {f"2026-0{m}": (3, 0) for m in range(3, 9)})
        cmgr, n_meses = compute_cmgr_engajamento(pd.DataFrame(rows), NOW)
        assert math.isnan(cmgr)
        assert n_meses < 4


def _perfil(url: str, username: str, followers: int = 1000) -> dict:
    return {"inputUrl": url, "username": username, "followersCount": followers}


def _reel(url: str, i: int, plays: int | None, likes: int, comments: int) -> dict:
    return {
        "id": f"r-{url}-{i}",
        "inputUrl": url,
        "videoPlayCount": plays,
        "likesCount": likes,
        "commentsCount": comments,
        "data_hora": pd.Timestamp("2024-01-10"),  # fora da janela de Consistencia
    }


def _coment(url: str, label: str, fonte: str = "comentario") -> dict:
    return {"inputUrl": url, "fonte": fonte, "sentiment_label": label}


def _cenario(n_perfis: int = 5):
    """n perfis com desempenho crescente (gov0 pior, ultimo melhor), todos com historico."""
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
        posts += _crescimento_10pct(url, n_meses=6)
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
        assert g1["consistencia"] == pytest.approx(0.10, abs=0.01)

    def test_normalizadas_entre_0_e_100_e_escore_e_media_com_pesos_iguais(self):
        perfis, reels, posts, sent = _cenario(5)
        out = _score(perfis, reels, posts, sent)
        for dim in DIMENSOES:
            assert out[f"{dim}_norm"].dropna().between(0, 100).all()
        linha = out.iloc[0]
        esperado = sum(linha[f"{d}_norm"] for d in DIMENSOES) / 5
        assert linha["escore"] == pytest.approx(esperado)
        assert (out["n_dimensoes"] == 5).all()

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
        posts = posts[
            posts["inputUrl"] != perfis.iloc[0]["inputUrl"]
        ]  # gov0 sem historico
        out = _score(perfis, reels, posts, sent).set_index("username")
        g0 = out.loc["gov0"]
        assert bool(g0["consistencia_pendente"]) is True
        assert math.isnan(g0["consistencia"]) and math.isnan(g0["consistencia_norm"])
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
        antes = _score(perfis, reels, posts, sent)
        duplicado = posts.iloc[[0, 1, 2]]  # mesmos ids repetidos
        depois = _score(perfis, reels, pd.concat([posts, duplicado]), sent)
        assert antes["consistencia"].tolist() == pytest.approx(
            depois["consistencia"].tolist()
        )


class TestWrite:
    def test_grava_no_schema_declarado(self, tmp_path):
        perfis, reels, posts, sent = _cenario(5)
        out = _score(perfis, reels, posts, sent)
        path = tmp_path / "governor_scorecard"
        GovernorScorecardScorer().write(
            out, path, "run-1", generated_at=datetime(2026, 10, 4, tzinfo=timezone.utc)
        )
        lido = DeltaTable(str(path)).to_pandas()
        assert len(lido) == 5
        assert set(lido["_run_id"]) == {"run-1"}
        assert lido["escore"].notna().all()

    def test_schema_exige_inputUrl_nao_nulo(self):
        perfis, reels, posts, sent = _cenario(2)
        out = _score(perfis, reels, posts, sent)
        out["_run_id"] = "r"
        out["_generated_at"] = datetime(2026, 10, 4, tzinfo=timezone.utc)
        out.loc[0, "inputUrl"] = None
        with pytest.raises(Exception):
            conform_to_schema(out, GOLD_GOVERNOR_SCORECARD_SCHEMA)
