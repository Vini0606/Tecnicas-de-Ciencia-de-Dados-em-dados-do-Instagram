"""Testes de `NsmScorer` (ADR 0020, Ficha 5 / issue #90).

NSM = (comentários positivos / comentários totais) x alcance médio, por
perfil. Lê `governor_sentiment` (fonte "comentario") para a proporção de
positivos e `governor_engagement` para o proxy de alcance médio
(`TOTAL ENGAJAMENTO / count`) -- ver docstring de `NsmScorer` para a
justificativa completa de cada componente e das convenções de "não
calculável"."""

from datetime import datetime, timezone

import pandas as pd
import pytest
from deltalake import DeltaTable

from src.delta_io import conform_to_schema
from src.features.gold.nsm_scorer import NsmScorer
from src.schemas_delta import GOLD_NSM_SCHEMA


def _comentario(**overrides) -> dict:
    row = {
        "inputUrl": "https://instagram.com/gov_a",
        "fonte": "comentario",
        "sentiment_label": "positive",
    }
    row.update(overrides)
    return row


def _engagement(**overrides) -> dict:
    row = {
        "inputUrl": "https://instagram.com/gov_a",
        "username": "gov_a",
        "TOTAL ENGAJAMENTO": 100,
        "count": 10,
    }
    row.update(overrides)
    return row


class TestFormula:
    def test_nsm_e_proporcao_positivos_vezes_alcance_medio(self):
        df_sentiment = pd.DataFrame(
            [
                _comentario(sentiment_label="positive"),
                _comentario(sentiment_label="positive"),
                _comentario(sentiment_label="negative"),
                _comentario(sentiment_label="negative"),
            ]
        )
        df_engagement = pd.DataFrame([_engagement(**{"TOTAL ENGAJAMENTO": 200, "count": 10})])

        out = NsmScorer().score(df_sentiment, df_engagement)

        linha = out.iloc[0]
        # proporcao_positivos = 2/4 = 0.5 ; alcance_medio = 200/10 = 20
        assert linha["proporcao_positivos"] == pytest.approx(0.5)
        assert linha["alcance_medio"] == pytest.approx(20.0)
        assert linha["nsm"] == pytest.approx(0.5 * 20.0)

    def test_ignora_linhas_de_fonte_legenda_e_transcricao(self):
        """NSM é só sobre comentário -- `governor_sentiment` também acumula
        legenda/transcrição (issue #88), que não deve contar como
        "comentário total" aqui."""
        df_sentiment = pd.DataFrame(
            [
                _comentario(sentiment_label="positive"),
                _comentario(sentiment_label="negative", fonte="legenda"),
                _comentario(sentiment_label="negative", fonte="transcricao"),
            ]
        )
        df_engagement = pd.DataFrame([_engagement()])

        out = NsmScorer().score(df_sentiment, df_engagement)

        linha = out.iloc[0]
        assert linha["n_comentarios_totais"] == 1
        assert linha["proporcao_positivos"] == pytest.approx(1.0)

    def test_funciona_sem_coluna_fonte(self):
        df_sentiment = pd.DataFrame([_comentario()]).drop(columns=["fonte"])
        df_engagement = pd.DataFrame([_engagement()])

        out = NsmScorer().score(df_sentiment, df_engagement)
        assert len(out) == 1


class TestCasosDeBorda:
    def test_perfil_com_zero_comentarios_nao_causa_divisao_por_zero(self):
        """Perfil existe em `governor_engagement` mas não tem nenhuma linha
        em `governor_sentiment` -- proporcao_positivos precisa ser um valor
        definido (0.0), nunca ZeroDivisionError nem NaN propagado."""
        df_sentiment = pd.DataFrame(columns=["inputUrl", "fonte", "sentiment_label"])
        df_engagement = pd.DataFrame([_engagement()])

        out = NsmScorer().score(df_sentiment, df_engagement)

        assert len(out) == 1
        linha = out.iloc[0]
        assert linha["n_comentarios_totais"] == 0
        assert linha["proporcao_positivos"] == 0.0
        assert not pd.isna(linha["proporcao_positivos"])
        assert linha["nsm"] == 0.0
        assert not pd.isna(linha["nsm"])

    def test_perfil_com_zero_posts_nao_causa_divisao_por_zero(self):
        """`count == 0` em `governor_engagement` -- alcance_medio precisa
        ser um valor definido (0.0), nunca ZeroDivisionError nem NaN."""
        df_sentiment = pd.DataFrame([_comentario(sentiment_label="positive")])
        df_engagement = pd.DataFrame(
            [_engagement(**{"TOTAL ENGAJAMENTO": 0, "count": 0})]
        )

        out = NsmScorer().score(df_sentiment, df_engagement)

        linha = out.iloc[0]
        assert linha["alcance_medio"] == 0.0
        assert linha["nsm"] == 0.0
        assert not pd.isna(linha["nsm"])

    def test_perfil_so_em_sentiment_sem_engagement_nao_quebra(self):
        """Merge outer -- um perfil pode existir em só uma das duas fontes
        (ex.: comentário chegou antes do agregado de engajamento rodar de
        novo). Não pode sumir do ranking nem quebrar."""
        df_sentiment = pd.DataFrame(
            [_comentario(inputUrl="https://instagram.com/gov_sem_engajamento")]
        )
        df_engagement = pd.DataFrame([_engagement()])

        out = NsmScorer().score(df_sentiment, df_engagement)

        assert len(out) == 2
        linha = out[out["inputUrl"] == "https://instagram.com/gov_sem_engajamento"].iloc[0]
        assert linha["alcance_medio"] == 0.0
        assert linha["nsm"] == 0.0

    def test_dataframe_de_sentimento_vazio_nao_quebra(self):
        df_sentiment = pd.DataFrame(columns=["inputUrl", "fonte", "sentiment_label"])
        df_engagement = pd.DataFrame([_engagement(), _engagement(inputUrl="https://instagram.com/gov_b")])

        out = NsmScorer().score(df_sentiment, df_engagement)

        assert len(out) == 2
        assert (out["nsm"] == 0.0).all()

    def test_falha_com_mensagem_clara_se_faltar_coluna_obrigatoria_em_sentiment(self):
        df_sentiment = pd.DataFrame([_comentario()]).drop(columns=["inputUrl"])
        df_engagement = pd.DataFrame([_engagement()])
        with pytest.raises(ValueError, match="inputUrl"):
            NsmScorer().score(df_sentiment, df_engagement)

    def test_falha_com_mensagem_clara_se_faltar_coluna_obrigatoria_em_engagement(self):
        df_sentiment = pd.DataFrame([_comentario()])
        df_engagement = pd.DataFrame([_engagement()]).drop(columns=["count"])
        with pytest.raises(ValueError, match="count"):
            NsmScorer().score(df_sentiment, df_engagement)


class TestRankingContrastaComEngajamentoBruto:
    def test_ranking_por_nsm_inverte_ranking_por_engajamento_bruto(self):
        """Caso de contraste explícito pedido pela issue #90: perfil A tem
        engajamento bruto ALTO mas sentimento predominantemente NEGATIVO;
        perfil B tem engajamento bruto menor mas sentimento predominantemente
        POSITIVO. O ranking por NSM deve inverter o ranking por engajamento
        bruto -- prova de que qualificar o engajamento muda a ordem."""
        df_sentiment = pd.DataFrame(
            # Perfil A: 9 negativos, 1 positivo (proporcao_positivos = 0.1).
            [_comentario(inputUrl="https://instagram.com/gov_a", sentiment_label="negative")] * 9
            + [_comentario(inputUrl="https://instagram.com/gov_a", sentiment_label="positive")]
            # Perfil B: 9 positivos, 1 negativo (proporcao_positivos = 0.9).
            + [_comentario(inputUrl="https://instagram.com/gov_b", sentiment_label="positive")] * 9
            + [_comentario(inputUrl="https://instagram.com/gov_b", sentiment_label="negative")]
        )
        df_engagement = pd.DataFrame(
            [
                # Perfil A: alcance_medio = 1000/10 = 100 (bruto alto).
                _engagement(
                    inputUrl="https://instagram.com/gov_a",
                    username="gov_a",
                    **{"TOTAL ENGAJAMENTO": 1000, "count": 10},
                ),
                # Perfil B: alcance_medio = 200/10 = 20 (bruto menor).
                _engagement(
                    inputUrl="https://instagram.com/gov_b",
                    username="gov_b",
                    **{"TOTAL ENGAJAMENTO": 200, "count": 10},
                ),
            ]
        )

        out = NsmScorer().score(df_sentiment, df_engagement)

        # Ranking bruto (por alcance_medio/engajamento): A (100) > B (20).
        ranking_bruto = (
            out.sort_values("alcance_medio", ascending=False)["inputUrl"].tolist()
        )
        assert ranking_bruto == [
            "https://instagram.com/gov_a",
            "https://instagram.com/gov_b",
        ]

        # NSM: A = 0.1 * 100 = 10 ; B = 0.9 * 20 = 18 -- B ultrapassa A.
        nsm_a = out.loc[out["inputUrl"] == "https://instagram.com/gov_a", "nsm"].iloc[0]
        nsm_b = out.loc[out["inputUrl"] == "https://instagram.com/gov_b", "nsm"].iloc[0]
        assert nsm_a == pytest.approx(10.0)
        assert nsm_b == pytest.approx(18.0)

        # `score()` já devolve ordenado por nsm decrescente -- ranking
        # qualificado inverte o ranking bruto.
        assert out["inputUrl"].tolist() == [
            "https://instagram.com/gov_b",
            "https://instagram.com/gov_a",
        ]


class TestDeterminismo:
    def test_ranking_ordenado_por_nsm_decrescente(self):
        df_sentiment = pd.DataFrame(
            [_comentario(inputUrl="https://instagram.com/gov_baixo", sentiment_label="negative")]
            + [_comentario(inputUrl="https://instagram.com/gov_alto", sentiment_label="positive")]
        )
        df_engagement = pd.DataFrame(
            [
                _engagement(inputUrl="https://instagram.com/gov_baixo", **{"TOTAL ENGAJAMENTO": 10, "count": 10}),
                _engagement(inputUrl="https://instagram.com/gov_alto", **{"TOTAL ENGAJAMENTO": 100, "count": 10}),
            ]
        )
        out = NsmScorer().score(df_sentiment, df_engagement)
        assert out.iloc[0]["inputUrl"] == "https://instagram.com/gov_alto"
        assert out["nsm"].is_monotonic_decreasing


class TestWrite:
    def test_write_grava_delta_conformado_ao_schema(self, tmp_path):
        df_scored = NsmScorer().score(
            pd.DataFrame([_comentario()]), pd.DataFrame([_engagement()])
        )
        path = tmp_path / "governor_nsm"

        NsmScorer().write(df_scored, path, run_id="r1")

        out = DeltaTable(str(path)).to_pandas()
        assert len(out) == 1
        assert out.loc[0, "_run_id"] == "r1"

    def test_write_aceita_generated_at_explicito(self, tmp_path):
        df_scored = NsmScorer().score(
            pd.DataFrame([_comentario()]), pd.DataFrame([_engagement()])
        )
        generated_at = datetime(2026, 5, 1, tzinfo=timezone.utc)

        NsmScorer().write(
            df_scored, tmp_path / "governor_nsm", run_id="r1", generated_at=generated_at
        )

        out = DeltaTable(str(tmp_path / "governor_nsm")).to_pandas()
        assert out.loc[0, "_generated_at"] == generated_at

    def test_write_conforma_ao_contrato_gold(self, tmp_path):
        df_scored = NsmScorer().score(
            pd.DataFrame(
                [_comentario(), _comentario(inputUrl="https://instagram.com/gov_b")]
            ),
            pd.DataFrame([_engagement(), _engagement(inputUrl="https://instagram.com/gov_b")]),
        )
        df_scored["_run_id"] = "r1"
        df_scored["_generated_at"] = datetime.now(timezone.utc)
        table = conform_to_schema(df_scored, GOLD_NSM_SCHEMA)
        assert table.num_rows == 2
