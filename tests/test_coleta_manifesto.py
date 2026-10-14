"""Manifesto do Snapshot (ADR 0039, issue #247)."""

import json
from datetime import date, datetime, timezone

import pandas as pd
import pyarrow as pa
import pytest

from src.coleta.manifesto import (
    escrever_manifesto,
    gerar_manifesto,
    validar_manifesto,
    versao_do_codigo,
)
from src.coleta.recorte import Recorte, gerar_tag
from src.data_extract.bronze_writer import BronzeWriter
from src.delta_io import write_delta
from src.schemas_delta import SILVER_UGC_MENTIONS_SCHEMA

SEGREDO = "hf_SEGREDO_NUNCA_NO_MANIFESTO"
COMENTARIO = "texto secreto do comentario da Maria Silva"
LEGENDA = "legenda privada com opiniao"
NOME_PESSOA = "Maria Silva Terceira"
EXTRAIDO = datetime(2026, 10, 9, 14, 30, tzinfo=timezone.utc)
RECORTE = Recorte(dias=90, teto=250)


@pytest.fixture
def snapshot(tmp_path):
    bronze = tmp_path / "bronze"
    writer = BronzeWriter(
        bronze / "instagram_profiles",
        bronze / "instagram_posts",
        bronze / "instagram_reels",
        bronze_ugc_mentions_path=bronze / "ugc_mentions",
    )
    writer.write_profiles(
        [{"id": "1", "username": "gov_a", "fullName": NOME_PESSOA}, {"id": "2", "username": "gov_b"}],
        run_id="r",
    )
    writer.write_posts(
        [
            {"id": "p1", "ownerUsername": "gov_a", "timestamp": "2026-08-01T10:00:00.000Z", "caption": LEGENDA},
            {
                "id": "p2",
                "ownerUsername": "gov_a",
                "timestamp": "2026-09-20T10:00:00.000Z",
                "caption": LEGENDA,
                "latestComments": [{"text": COMENTARIO, "ownerUsername": "maria_silva"}],
            },
            {"id": "p3", "ownerUsername": "gov_b", "timestamp": "2026-09-01T10:00:00.000Z"},
        ],
        run_id="r",
    )
    writer.write_reels(
        [
            {
                "id": "r1",
                "ownerUsername": "gov_b",
                "timestamp": "2026-07-15T10:00:00.000Z",
                "latestComments": [{"text": COMENTARIO}],
            }
        ],
        run_id="r",
    )
    writer.write_ugc_mentions(
        [
            {
                "id": "u1",
                "ownerUsername": "maria_silva",
                "ownerFullName": NOME_PESSOA,
                "caption": LEGENDA,
                "timestamp": "2026-09-10T10:00:00.000Z",
            },
            {"id": "u2", "ownerUsername": "outro_terceiro", "timestamp": "2026-09-12T10:00:00.000Z"},
        ],
        run_id="r",
    )
    silver_ugc = pd.DataFrame(
        {
            "id": ["u1", "u2"],
            "governor_username": ["gov_a", "gov_a"],
            "authorUsername": ["maria_silva", "outro_terceiro"],
            "caption": [LEGENDA, LEGENDA],
            "paidPartnership": [False, False],
            "likesCount": [1, 2],
            "commentsCount": [0, 0],
            "data_hora": pd.to_datetime(["2026-09-10", "2026-09-12"]),
            "_ingested_at": pd.Timestamp("2026-10-09", tz="UTC"),
            "_run_id": "r",
            "_source_layer": "bronze",
        }
    )
    write_delta(tmp_path / "silver" / "ugc_mentions", silver_ugc, SILVER_UGC_MENTIONS_SCHEMA)
    write_delta(
        tmp_path / "gold" / "governor_engagement",
        pd.DataFrame({"username": ["gov_a", "gov_b"]}),
        pa.schema([("username", pa.string())]),
    )
    return tmp_path


def _gerar(snapshot, **kw):
    args = dict(
        tag=gerar_tag(RECORTE, date(2026, 10, 9)),
        recorte=RECORTE,
        extraido_em=EXTRAIDO,
        versao_codigo="abc123def456",
        custo_estimado={"posts_reels": 1.5, "ugc": 0.5, "total": 2.0},
    )
    args.update(kw)
    return gerar_manifesto(snapshot, **args)


def test_manifesto_traz_todos_os_campos_e_valida(snapshot):
    m = _gerar(snapshot, custo_real=1.8)

    assert m["versao_esquema"] == 2
    assert m["identidade"] == {
        "tag": "coleta_2026-10-09_ultimos-90d_teto-250",
        "extraido_em": "2026-10-09T14:30:00+00:00",
        "versao_codigo": "abc123def456",
    }
    assert m["recorte"] == {"dias": 90, "inicio": None, "fim": None, "teto": 250}
    assert m["recorte_efetivo"] == {"inicio": "2026-07-11", "fim": "2026-10-09"}
    assert m["custo"] == {"estimado": {"posts_reels": 1.5, "ugc": 0.5, "total": 2.0}, "real": 1.8}
    tabelas = {(t["camada"], t["nome"]): t["linhas"] for t in m["tabelas"]}
    assert tabelas == {
        ("bronze", "instagram_profiles"): 2,
        ("bronze", "instagram_posts"): 3,
        ("bronze", "instagram_reels"): 1,
        ("bronze", "ugc_mentions"): 2,
        ("silver", "ugc_mentions"): 2,
        ("gold", "governor_engagement"): 2,
    }
    validar_manifesto(m)


def test_cobertura_por_perfil_bate_com_o_snapshot(snapshot):
    cob = _gerar(snapshot)["cobertura"]

    assert cob["posts"]["itens"] == 3
    assert (cob["posts"]["mais_antiga"], cob["posts"]["mais_recente"]) == ("2026-08-01", "2026-09-20")
    assert cob["posts"]["por_perfil"] == [
        {"username": "gov_a", "itens": 2, "mais_antiga": "2026-08-01", "mais_recente": "2026-09-20"},
        {"username": "gov_b", "itens": 1, "mais_antiga": "2026-09-01", "mais_recente": "2026-09-01"},
    ]
    assert cob["reels"]["por_perfil"] == [
        {"username": "gov_b", "itens": 1, "mais_antiga": "2026-07-15", "mais_recente": "2026-07-15"}
    ]
    assert cob["perfis"]["itens"] == 2
    assert cob["ugc"]["itens"] == 2
    assert cob["ugc"]["por_perfil"] == [
        {"username": "gov_a", "itens": 2, "mais_antiga": "2026-09-10", "mais_recente": "2026-09-12"}
    ]


def test_nenhum_texto_nome_ou_segredo_entra_no_manifesto(snapshot, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", SEGREDO)
    m = _gerar(snapshot)
    destino = escrever_manifesto(snapshot, m)
    conteudo = destino.read_text(encoding="utf-8")

    for proibido in (SEGREDO, COMENTARIO, LEGENDA, NOME_PESSOA, "maria_silva", "outro_terceiro", "Maria"):
        assert proibido not in conteudo
    assert json.loads(conteudo) == m


def test_snapshot_vazio_gera_manifesto_valido(tmp_path):
    m = _gerar(tmp_path)
    assert m["tabelas"] == []
    assert m["cobertura"]["posts"] == {"itens": 0, "mais_antiga": None, "mais_recente": None, "por_perfil": []}
    assert m["custo"]["real"] is None


def test_recorte_absoluto_e_custo_ausente(tmp_path):
    recorte = Recorte(inicio=date(2026, 3, 1), fim=date(2026, 6, 30))
    m = _gerar(tmp_path, recorte=recorte, tag=gerar_tag(recorte, date(2026, 10, 9)), custo_estimado=None)
    assert m["recorte"]["inicio"] == "2026-03-01"
    assert m["recorte_efetivo"] == {"inicio": "2026-03-01", "fim": "2026-06-30"}
    assert m["custo"] == {"estimado": None, "real": None}


def test_manifesto_grava_a_estimativa_de_custo_com_esperado_e_pior_caso(tmp_path):
    from src.coleta.custo import estimar_custo

    custo = estimar_custo(RECORTE, 26, date(2026, 10, 9))
    m = _gerar(tmp_path, custo_estimado=custo)
    validar_manifesto(m)
    assert m["custo"]["estimado"]["total"] == custo["total"]
    assert m["custo"]["estimado"]["pior_caso_total"] == custo["pior_caso_total"]


def test_recorte_so_com_teto_nao_tem_janela_efetiva(tmp_path):
    recorte = Recorte(teto=10)
    m = _gerar(tmp_path, recorte=recorte, tag=gerar_tag(recorte, date(2026, 10, 9)))
    assert m["recorte_efetivo"] is None
    validar_manifesto(m)


def test_manifesto_v1_sem_recorte_efetivo_continua_valido(snapshot):
    m = _gerar(snapshot)
    m["versao_esquema"] = 1
    del m["recorte_efetivo"]
    validar_manifesto(m)

    m["recorte_efetivo"] = None  # campo da v2 numa v1: recusado
    with pytest.raises(ValueError, match="chaves"):
        validar_manifesto(m)


def test_manifesto_v2_exige_recorte_efetivo_coerente(snapshot):
    m = _gerar(snapshot)
    sem_campo = {k: v for k, v in m.items() if k != "recorte_efetivo"}
    with pytest.raises(ValueError, match="chaves"):
        validar_manifesto(sem_campo)

    invertido = json.loads(json.dumps(m))
    invertido["recorte_efetivo"] = {"inicio": "2026-10-09", "fim": "2026-07-11"}
    with pytest.raises(ValueError, match="inicio depois de fim"):
        validar_manifesto(invertido)

    incompleto = json.loads(json.dumps(m))
    incompleto["recorte_efetivo"] = {"inicio": "2026-07-11", "fim": None}
    with pytest.raises(ValueError, match="obrigatória"):
        validar_manifesto(incompleto)


def test_esquema_recusa_campo_extra_tag_ruim_e_data_invalida(snapshot):
    m = _gerar(snapshot)

    com_texto = json.loads(json.dumps(m))
    com_texto["cobertura"]["posts"]["por_perfil"][0]["comentario"] = COMENTARIO
    with pytest.raises(ValueError, match="chaves"):
        validar_manifesto(com_texto)

    tag_ruim = json.loads(json.dumps(m))
    tag_ruim["identidade"]["tag"] = "qualquer coisa"
    with pytest.raises(ValueError, match="tag"):
        validar_manifesto(tag_ruim)

    data_ruim = json.loads(json.dumps(m))
    data_ruim["cobertura"]["posts"]["mais_antiga"] = "ontem"
    with pytest.raises(ValueError, match="data"):
        validar_manifesto(data_ruim)

    sem_chave = json.loads(json.dumps(m))
    del sem_chave["custo"]
    with pytest.raises(ValueError, match="chaves"):
        validar_manifesto(sem_chave)


def test_versao_do_codigo_e_hash_git_ou_desconhecida(tmp_path):
    assert versao_do_codigo(tmp_path) == "desconhecida"
    assert versao_do_codigo() != ""
