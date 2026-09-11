"""Testes de `TopicPriorityScorer` (ADR 0020, Ficha 6 / issue #91).

Score ICE = Impacto x Confiança x Facilidade, por tópico de COMENTÁRIO (não
de discurso oficial) -- lê só `governor_sentiment`, mesma dependência da
NSM (Ficha 5). Ver docstring de `TopicPriorityScorer` para a justificativa
completa de cada componente."""

from datetime import datetime, timezone

import pandas as pd
import pytest
from deltalake import DeltaTable

from src.delta_io import conform_to_schema
from src.features.gold.topic_priority_scorer import TopicPriorityScorer
from src.schemas_delta import GOLD_TOPIC_PRIORITY_SCORE_SCHEMA


def _comentario(**overrides) -> dict:
    row = {
        "id_reel": "r1",
        "id_comment": "c1",
        "text": "ótimo trabalho na saúde",
        "fonte": "comentario",
        "likesCount": 5,
        "repliesCount": 1,
        "sentiment_label": "positive",
        "sentiment_score": 0.9,
        "Topic": 3,
        "Name": "3_saude_hospital",
    }
    row.update(overrides)
    return row


def _legenda(**overrides) -> dict:
    """Linha de `fonte="legenda"` -- nunca passa por BERTopic de comentário
    (ADR 0020 Ficha 3 / issue #88): `Topic`/`Name` ficam nulos. Precisa ser
    ignorada pelo Score ICE, não misturada aos tópicos de comentário."""
    row = {
        "id_reel": "p1",
        "id_comment": pd.NA,
        "text": "Anunciamos hoje um investimento em saúde.",
        "fonte": "legenda",
        "likesCount": pd.NA,
        "repliesCount": pd.NA,
        "sentiment_label": "positive",
        "sentiment_score": 0.8,
        "Topic": pd.NA,
        "Name": pd.NA,
    }
    row.update(overrides)
    return row


class TestScoreComponentesEFormula:
    def test_score_e_produto_das_tres_componentes(self):
        df = pd.DataFrame(
            [
                _comentario(likesCount=9, repliesCount=0, sentiment_score=0.8),
            ]
        )
        out = TopicPriorityScorer().score(df)
        linha = out.iloc[0]
        # alcance_topico=9 -> alcance_normalizado = 9/(9+1) = 0.9
        # proporcao_sentimento_positivo = 1.0 (o único comentário é positivo)
        # impacto = 0.9 * 1.0 = 0.9
        # confianca = 0.8 (média de sentiment_score)
        # facilidade = 1.0 (v1)
        assert linha["alcance_normalizado"] == pytest.approx(0.9)
        assert linha["proporcao_sentimento_positivo"] == pytest.approx(1.0)
        assert linha["impacto"] == pytest.approx(0.9)
        assert linha["confianca"] == pytest.approx(0.8)
        assert linha["facilidade"] == pytest.approx(1.0)
        assert linha["score"] == pytest.approx(0.9 * 0.8 * 1.0)

    def test_agrega_por_topico_nao_por_comentario(self):
        df = pd.DataFrame(
            [
                _comentario(id_comment="c1", likesCount=1, repliesCount=0),
                _comentario(id_comment="c2", likesCount=1, repliesCount=0),
                _comentario(id_comment="c3", likesCount=1, repliesCount=0),
            ]
        )
        out = TopicPriorityScorer().score(df)
        assert len(out) == 1
        assert out.iloc[0]["n_comentarios"] == 3
        assert out.iloc[0]["alcance_topico"] == 3


class TestFiltragemDeEscopo:
    def test_ignora_linhas_de_fonte_legenda_e_transcricao(self):
        """Score ICE é só sobre tópico de comentário -- `governor_sentiment`
        acumula legenda/transcrição na mesma tabela (issue #88), mas essas
        linhas não têm Topic/Name de BERTopic de comentário."""
        df = pd.DataFrame(
            [
                _comentario(),
                _legenda(),
                _legenda(fonte="transcricao"),
            ]
        )
        out = TopicPriorityScorer().score(df)
        assert len(out) == 1
        assert out.iloc[0]["Topic"] == 3

    def test_funciona_sem_coluna_fonte(self):
        """Chamadores antigos/teste sintético podem não ter a coluna
        `fonte` -- não deve quebrar, só não filtra por fonte."""
        df = pd.DataFrame([_comentario()]).drop(columns=["fonte"])
        out = TopicPriorityScorer().score(df)
        assert len(out) == 1

    def test_ignora_topico_outlier_menos_um(self):
        """Topic == -1 é o rótulo de ruído/outlier do BERTopic -- não é um
        tema coerente para priorizar produção de conteúdo."""
        df = pd.DataFrame(
            [
                _comentario(Topic=-1, Name="-1_ruido"),
                _comentario(id_comment="c2", Topic=7, Name="7_educacao"),
            ]
        )
        out = TopicPriorityScorer().score(df)
        assert len(out) == 1
        assert out.iloc[0]["Topic"] == 7

    def test_falha_com_mensagem_clara_se_faltar_coluna_obrigatoria(self):
        df = pd.DataFrame([_comentario()]).drop(columns=["sentiment_score"])
        with pytest.raises(ValueError, match="sentiment_score"):
            TopicPriorityScorer().score(df)


class TestCasosDeBorda:
    def test_dataframe_vazio_nao_quebra(self):
        out = TopicPriorityScorer().score(pd.DataFrame(columns=[
            "Topic", "Name", "sentiment_label", "sentiment_score",
            "fonte", "likesCount", "repliesCount",
        ]))
        assert out.empty
        assert set(GOLD_TOPIC_PRIORITY_SCORE_SCHEMA.names) - {"_run_id", "_generated_at"} <= set(
            out.columns
        )

    def test_so_linhas_de_legenda_transcricao_resulta_em_vazio_sem_erro(self):
        """Nenhum comentário sobra depois do filtro de fonte/Topic -- não
        pode gerar ZeroDivisionError nem NaN propagado, só um resultado
        vazio bem formado."""
        df = pd.DataFrame([_legenda(), _legenda(fonte="transcricao")])
        out = TopicPriorityScorer().score(df)
        assert out.empty

    def test_topico_sem_engajamento_nao_causa_divisao_por_zero(self):
        """likesCount=repliesCount=0 -> alcance_topico=0 -> normalização
        0/(0+1)=0.0, nunca ZeroDivisionError nem NaN."""
        df = pd.DataFrame([_comentario(likesCount=0, repliesCount=0)])
        out = TopicPriorityScorer().score(df)
        linha = out.iloc[0]
        assert linha["alcance_topico"] == 0
        assert linha["alcance_normalizado"] == 0.0
        assert linha["impacto"] == 0.0
        assert linha["score"] == 0.0
        assert not pd.isna(linha["score"])

    def test_sentiment_score_nulo_nao_quebra_media_de_confianca(self):
        df = pd.DataFrame(
            [
                _comentario(id_comment="c1", sentiment_score=pd.NA),
                _comentario(id_comment="c2", sentiment_score=0.6),
            ]
        )
        out = TopicPriorityScorer().score(df)
        assert not pd.isna(out.iloc[0]["confianca"])


class TestDeterminismo:
    def test_score_e_ranking_sao_deterministicos(self):
        df = pd.DataFrame(
            [
                _comentario(id_comment="c1", Topic=1, Name="1_a", likesCount=50, sentiment_score=0.9),
                _comentario(id_comment="c2", Topic=2, Name="2_b", likesCount=1, sentiment_score=0.3),
                _comentario(
                    id_comment="c3", Topic=3, Name="3_c", likesCount=5,
                    sentiment_label="negative", sentiment_score=0.7,
                ),
            ]
        )
        out1 = TopicPriorityScorer().score(df)
        out2 = TopicPriorityScorer().score(df.sample(frac=1, random_state=1))

        assert out1["Topic"].tolist() == out2["Topic"].tolist()
        pd.testing.assert_series_equal(
            out1["score"].reset_index(drop=True),
            out2["score"].reset_index(drop=True),
        )

    def test_ranking_ordenado_por_score_decrescente(self):
        df = pd.DataFrame(
            [
                _comentario(id_comment="c1", Topic=1, Name="1_baixo", likesCount=0, sentiment_score=0.1),
                _comentario(id_comment="c2", Topic=2, Name="2_alto", likesCount=100, sentiment_score=0.99),
            ]
        )
        out = TopicPriorityScorer().score(df)
        assert out.iloc[0]["Topic"] == 2
        assert out["score"].is_monotonic_decreasing


class TestIntervaloDasComponentes:
    def test_componentes_ficam_no_intervalo_documentado(self):
        """proporcao_sentimento_positivo e confianca em [0, 1] (médias de
        indicadores/scores em [0,1]); alcance_normalizado em [0, 1)
        (x/(x+1), nunca atinge 1); facilidade == 1.0 fixa (v1); score em
        [0, 1) (produto de componentes <= 1, com alcance_normalizado < 1)."""
        df = pd.DataFrame(
            [
                _comentario(id_comment="c1", Topic=1, Name="1_a", likesCount=1000, sentiment_score=1.0),
                _comentario(
                    id_comment="c2", Topic=2, Name="2_b", likesCount=0, repliesCount=0,
                    sentiment_label="negative", sentiment_score=0.0,
                ),
            ]
        )
        out = TopicPriorityScorer().score(df)
        assert ((out["proporcao_sentimento_positivo"] >= 0) & (out["proporcao_sentimento_positivo"] <= 1)).all()
        assert ((out["confianca"] >= 0) & (out["confianca"] <= 1)).all()
        assert ((out["alcance_normalizado"] >= 0) & (out["alcance_normalizado"] < 1)).all()
        assert ((out["impacto"] >= 0) & (out["impacto"] < 1)).all()
        assert (out["facilidade"] == 1.0).all()
        assert ((out["score"] >= 0) & (out["score"] < 1)).all()


class TestWrite:
    def test_write_grava_delta_conformado_ao_schema(self, tmp_path):
        df_scored = TopicPriorityScorer().score(pd.DataFrame([_comentario()]))
        path = tmp_path / "topic_priority_score"

        TopicPriorityScorer().write(df_scored, path, run_id="r1")

        out = DeltaTable(str(path)).to_pandas()
        assert len(out) == 1
        assert out.loc[0, "Topic"] == 3
        assert out.loc[0, "_run_id"] == "r1"

    def test_write_aceita_generated_at_explicito(self, tmp_path):
        df_scored = TopicPriorityScorer().score(pd.DataFrame([_comentario()]))
        generated_at = datetime(2026, 5, 1, tzinfo=timezone.utc)

        TopicPriorityScorer().write(
            df_scored, tmp_path / "topic_priority_score", run_id="r1", generated_at=generated_at
        )

        out = DeltaTable(str(tmp_path / "topic_priority_score")).to_pandas()
        assert out.loc[0, "_generated_at"] == generated_at

    def test_write_conforma_ao_contrato_gold(self, tmp_path):
        df_scored = TopicPriorityScorer().score(
            pd.DataFrame([_comentario(), _comentario(id_comment="c2", Topic=7, Name="7_x")])
        )
        df_scored["_run_id"] = "r1"
        df_scored["_generated_at"] = datetime.now(timezone.utc)
        table = conform_to_schema(df_scored, GOLD_TOPIC_PRIORITY_SCORE_SCHEMA)
        assert table.num_rows == 2
