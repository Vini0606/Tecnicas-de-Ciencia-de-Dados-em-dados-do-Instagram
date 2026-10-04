"""Testes de `ContentTopicPriorityScorer` (issue #190, spec #182): Score ICE
por PAUTA (topico de discurso da legenda do reel), com os comentarios
agrupados pela pauta do reel em que foram feitos."""

from datetime import datetime, timezone

import pandas as pd
import pytest
from deltalake import DeltaTable

from src.features.gold.content_topic_priority_scorer import (
    ContentTopicPriorityScorer,
    clean_pauta_label,
)
from src.schemas_delta import GOLD_CONTENT_TOPIC_PRIORITY_SCORE_SCHEMA


def _comment(id_reel="r1", label="positive", score=0.9, likes=2, replies=0, **kw):
    row = {
        "id_reel": id_reel,
        "id_comment": f"c-{id_reel}-{label}-{likes}-{score}",
        "fonte": "comentario",
        "likesCount": likes,
        "repliesCount": replies,
        "sentiment_label": label,
        "sentiment_score": score,
        "Topic": 5,
        "Name": "5_comentario",
    }
    row.update(kw)
    return row


def _discourse(id_reel="r1", topic=0, name="0_Saude publica", fonte="legenda"):
    return {"id_reel": id_reel, "fonte": fonte, "Topic": topic, "Name": name}


def _score(comments, discourse):
    return ContentTopicPriorityScorer().score(pd.DataFrame(comments), pd.DataFrame(discourse))


def test_formula_e_contagens():
    out = _score(
        [
            _comment(label="positive", score=0.8, likes=3, replies=0),
            _comment(label="positive", score=0.6, likes=0, replies=0),
            _comment(label="negative", score=0.7, likes=0, replies=0),
            _comment(label="neutral", score=0.5, likes=0, replies=0),
        ],
        [_discourse()],
    )
    row = out.iloc[0]
    assert row["Topic"] == 0
    assert row["Name"] == "Saude publica"
    assert row["n_reels"] == 1
    assert row["n_comentarios"] == 4
    assert row["n_comentarios_positivos"] == 2
    assert row["n_comentarios_negativos"] == 1
    assert row["proporcao_sentimento_positivo"] == pytest.approx(0.5)
    assert row["alcance_pauta"] == 3
    assert row["alcance_normalizado"] == pytest.approx(3 / 4)
    assert row["confianca"] == pytest.approx((0.8 + 0.6 + 0.7 + 0.5) / 4)
    assert row["impacto"] == pytest.approx(0.75 * 0.5)
    assert row["facilidade"] == 1.0
    assert row["score"] == pytest.approx(row["impacto"] * row["confianca"])


def test_reel_duplicado_legenda_e_transcricao_conta_uma_vez():
    out = _score(
        [_comment()],
        [
            _discourse(topic=0, fonte="legenda"),
            _discourse(topic=7, name="7_outro", fonte="transcricao"),
            _discourse(topic=0, fonte="legenda"),
        ],
    )
    assert list(out["Topic"]) == [0]
    assert out.iloc[0]["n_reels"] == 1
    assert out.iloc[0]["n_comentarios"] == 1


def test_comentario_de_reel_sem_pauta_e_ignorado():
    out = _score([_comment("r1"), _comment("r2", likes=9)], [_discourse("r1")])
    assert out.iloc[0]["n_comentarios"] == 1
    assert out.iloc[0]["alcance_pauta"] == 2


def test_ruido_fora():
    out = _score(
        [_comment("r1"), _comment("r2")],
        [_discourse("r1", -1, "-1_x"), _discourse("r2")],
    )
    assert list(out["Topic"]) == [0]


def test_reel_so_com_transcricao_fica_fora():
    out = _score([_comment("r1")], [_discourse("r1", fonte="transcricao")])
    assert out.empty


def test_linhas_que_nao_sao_comentario_sao_ignoradas():
    out = _score([_comment(), _comment(fonte="legenda", id_comment=None)], [_discourse()])
    assert out.iloc[0]["n_comentarios"] == 1


def test_ordenacao_por_score_com_desempate_por_topic():
    comments = [
        _comment("a", score=0.5),
        _comment("b", score=0.5),
        _comment("c", score=0.9, likes=50),
    ]
    discourse = [
        _discourse("a", 2, "2_x"),
        _discourse("b", 1, "1_y"),
        _discourse("c", 3, "3_z"),
    ]
    out = _score(comments, discourse)
    assert list(out["Topic"]) == [3, 1, 2]


def test_pauta_sem_comentario_positivo_tem_score_zero():
    out = _score([_comment(label="negative"), _comment(label="neutral", likes=1)], [_discourse()])
    row = out.iloc[0]
    assert row["proporcao_sentimento_positivo"] == 0
    assert row["score"] == 0
    assert row["n_comentarios_negativos"] == 1


def test_sentiment_score_nulo_nao_propaga_nan():
    out = _score([_comment(score=None), _comment(score=0.5, likes=1)], [_discourse()])
    assert out.iloc[0]["confianca"] == pytest.approx(0.5)
    out = _score([_comment(score=None)], [_discourse()])
    assert out.iloc[0]["confianca"] == 0.0
    assert not out["score"].isna().any()


def test_tabelas_vazias_devolvem_schema_vazio():
    empty_c = pd.DataFrame(columns=["id_reel", "fonte", "sentiment_label", "sentiment_score"])
    empty_d = pd.DataFrame(columns=["id_reel", "fonte", "Topic", "Name"])
    out = ContentTopicPriorityScorer().score(empty_c, empty_d)
    assert out.empty
    assert "score" in out.columns


def test_colunas_ausentes_falham():
    with pytest.raises(ValueError):
        ContentTopicPriorityScorer().score(pd.DataFrame({"x": [1]}), pd.DataFrame({"y": [1]}))


def test_varios_reels_e_comentarios_na_mesma_pauta():
    out = _score(
        [_comment("r1"), _comment("r1", likes=1), _comment("r2")],
        [_discourse("r1"), _discourse("r2")],
    )
    assert out.iloc[0]["n_reels"] == 2
    assert out.iloc[0]["n_comentarios"] == 3


@pytest.mark.parametrize(
    "name, topic, expected",
    [
        ("0_Saude publica", 0, "Saude publica"),
        ("12_Obras viarias_estrada_obra_ponte_rodovia", 12, "Obras viarias"),
        ("3_saude_hospital_medico_ubs", 3, "saude, hospital, medico, ubs"),
        ("1____", 1, "sem assunto definido"),
        ("sem assunto definido", 4, "sem assunto definido"),
        (None, 4, "sem assunto definido"),
    ],
)
def test_clean_pauta_label(name, topic, expected):
    assert clean_pauta_label(name, topic) == expected


def test_write_grava_schema_e_metadados(tmp_path):
    scorer = ContentTopicPriorityScorer()
    df = _score([_comment()], [_discourse()])
    path = tmp_path / "content_topic_priority_score"
    scorer.write(df, path, "run_x", generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    out = DeltaTable(str(path)).to_pandas()
    assert (out["_run_id"] == "run_x").all()
    assert set(GOLD_CONTENT_TOPIC_PRIORITY_SCORE_SCHEMA.names) == set(out.columns)
