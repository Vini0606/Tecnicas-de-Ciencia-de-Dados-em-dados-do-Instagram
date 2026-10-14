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
from src.coleta.custo import agregar_custo_real, estimar_custo
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
EXECUCOES = [
    {"colecao": "perfis", "usd": 0.07, "itens": 2},
    {"colecao": "posts", "usd": 0.70, "itens": 3},
    {"colecao": "reels", "usd": 0.40, "itens": 1},
    {"colecao": "ugc", "usd": 0.25, "itens": 2},
]


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
        custo_estimado=estimar_custo(RECORTE, 2, date(2026, 10, 9)),
    )
    args.update(kw)
    return gerar_manifesto(snapshot, **args)


def test_manifesto_traz_todos_os_campos_e_valida(snapshot):
    m = _gerar(snapshot, custo_real=agregar_custo_real(EXECUCOES))

    assert m["versao_esquema"] == 4
    assert m["identidade"] == {
        "tag": "coleta_2026-10-09_ultimos-90d_teto-250",
        "extraido_em": "2026-10-09T14:30:00+00:00",
        "versao_codigo": "abc123def456",
    }
    assert m["recorte"] == {"dias": 90, "teto": 250}  # v3: só as chaves que se aplicam
    assert m["recorte_efetivo"] == {"inicio": "2026-07-11", "fim": "2026-10-09"}
    assert set(m["custo"]) == {"estimado", "real", "diferenca"}
    assert m["custo"]["estimado"] == estimar_custo(RECORTE, 2, date(2026, 10, 9))
    assert m["custo"]["real"]["custo_usd"]["total"] == 1.42
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
    # UGC: data de publicação; perfis não têm publicação, então a data é a da captura (_ingested_at)
    assert (cob["ugc"]["mais_antiga"], cob["ugc"]["mais_recente"]) == ("2026-09-10", "2026-09-12")
    assert cob["perfis"]["mais_antiga"] == cob["perfis"]["mais_recente"] == datetime.now(timezone.utc).date().isoformat()
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
    assert "real" not in m["custo"] and "diferenca" not in m["custo"]  # v4 nunca grava null: omite o bloco


def test_recorte_absoluto_e_custo_ausente(tmp_path):
    recorte = Recorte(inicio=date(2026, 3, 1), fim=date(2026, 6, 30))
    m = _gerar(tmp_path, recorte=recorte, tag=gerar_tag(recorte, date(2026, 10, 9)), custo_estimado=None)
    assert m["recorte"]["inicio"] == "2026-03-01"
    assert m["recorte_efetivo"] == {"inicio": "2026-03-01", "fim": "2026-06-30"}
    assert m["custo"] == {}  # sem estimativa nem custo real, o bloco fica vazio, sem nulos
    validar_manifesto(m)


def test_manifesto_grava_a_estimativa_com_estimado_maximo_resultados_teto_e_base(tmp_path):
    custo = estimar_custo(RECORTE, 26, date(2026, 10, 9))
    m = _gerar(tmp_path, custo_estimado=custo)
    validar_manifesto(m)
    estimado = m["custo"]["estimado"]
    assert set(estimado) == {"estimado_usd", "maximo_usd", "resultados_itens", "teto", "base_calibracao"}
    assert estimado["estimado_usd"]["total"] == custo["estimado_usd"]["total"]
    assert estimado["maximo_usd"]["total"] == custo["maximo_usd"]["total"]
    assert estimado["teto"] == {"aplicado_itens_por_perfil": 250, "padrao": False}
    assert set(estimado["base_calibracao"].values()) == {"sem_base"}


def test_diferenca_do_manifesto_e_real_menos_estimado_em_percentual(tmp_path):
    m = _gerar(tmp_path, custo_real=agregar_custo_real(EXECUCOES))
    est = m["custo"]["estimado"]

    dif = m["custo"]["diferenca"]
    assert set(dif) == {"custo_pct", "resultados_pct"}
    assert dif["resultados_pct"]["posts"] == round((3 - est["resultados_itens"]["posts"]) / est["resultados_itens"]["posts"] * 100, 1)
    assert dif["custo_pct"]["total"] < 0  # gastou menos que o estimado


def test_v4_recusa_estimado_acima_do_maximo_e_chave_sem_unidade(tmp_path):
    m = _gerar(tmp_path)

    acima = json.loads(json.dumps(m))
    acima["custo"]["estimado"]["estimado_usd"]["posts"] = acima["custo"]["estimado"]["maximo_usd"]["posts"] + 1
    with pytest.raises(ValueError, match="acima do máximo"):
        validar_manifesto(acima)

    antigo = json.loads(json.dumps(m))
    antigo["custo"]["estimado"]["total"] = 1.0  # chave do formato antigo, sem unidade
    with pytest.raises(ValueError, match="chaves"):
        validar_manifesto(antigo)

    teto_ruim = json.loads(json.dumps(m))
    teto_ruim["custo"]["estimado"]["teto"]["padrao"] = "sim"
    with pytest.raises(ValueError, match="booleano"):
        validar_manifesto(teto_ruim)

    base_nula = json.loads(json.dumps(m))
    base_nula["custo"]["estimado"]["base_calibracao"]["ugc"] = None
    with pytest.raises(ValueError, match="base_calibracao"):
        validar_manifesto(base_nula)


def test_manifestos_v1_v2_e_v3_continuam_validos_com_o_custo_antigo(snapshot):
    for versao in (1, 2, 3):
        m = _gerar(snapshot)
        m["versao_esquema"] = versao
        if versao == 1:
            del m["recorte_efetivo"]
        if versao < 3:
            m["recorte"] = {"dias": 90, "inicio": None, "fim": None, "teto": 250}
        m["custo"] = {"estimado": {"posts_reels": 1.5, "ugc": 0.5, "total": 2.0}, "real": 1.8 if versao == 1 else None}
        validar_manifesto(m)


def test_recorte_so_com_teto_nao_tem_janela_efetiva(tmp_path):
    recorte = Recorte(teto=10)
    m = _gerar(tmp_path, recorte=recorte, tag=gerar_tag(recorte, date(2026, 10, 9)))
    assert m["recorte_efetivo"] is None
    validar_manifesto(m)


def test_manifesto_v1_sem_recorte_efetivo_continua_valido(snapshot):
    m = _gerar(snapshot)
    m["versao_esquema"] = 1
    del m["recorte_efetivo"]
    m["recorte"] = {"dias": 90, "inicio": None, "fim": None, "teto": 250}  # v1/v2 gravam todas as chaves
    m["custo"] = {"estimado": None, "real": None}  # custo do formato antigo
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


def test_recorte_v3_nao_grava_chave_nula_e_recusa_chave_estranha(snapshot):
    m = _gerar(snapshot)
    assert all(v is not None for v in m["recorte"].values())

    com_nulo = json.loads(json.dumps(m))
    com_nulo["recorte"]["inicio"] = None
    with pytest.raises(ValueError, match="nula"):
        validar_manifesto(com_nulo)

    estranha = json.loads(json.dumps(m))
    estranha["recorte"]["texto"] = "x"
    with pytest.raises(ValueError, match="chaves"):
        validar_manifesto(estranha)


def test_manifesto_v2_com_chaves_nulas_no_recorte_continua_valido(snapshot):
    m = _gerar(snapshot)
    m["versao_esquema"] = 2
    m["recorte"] = {"dias": 5, "inicio": None, "fim": None, "teto": 30}
    m["custo"] = {"estimado": None, "real": None}
    validar_manifesto(m)


def test_recorte_absoluto_sem_teto_so_grava_inicio_e_fim(tmp_path):
    recorte = Recorte(inicio=date(2026, 3, 1), fim=date(2026, 6, 30))
    m = _gerar(tmp_path, recorte=recorte, tag=gerar_tag(recorte, date(2026, 10, 9)))
    assert m["recorte"] == {"inicio": "2026-03-01", "fim": "2026-06-30"}


def _nulos(o, caminho=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _nulos(v, f"{caminho}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _nulos(v, f"{caminho}[{i}]")
    elif o is None:
        yield caminho


def test_manifesto_v4_completo_nao_tem_nenhum_campo_nulo(snapshot):
    m = _gerar(snapshot, custo_real=agregar_custo_real(EXECUCOES))

    assert list(_nulos(m)) == []
