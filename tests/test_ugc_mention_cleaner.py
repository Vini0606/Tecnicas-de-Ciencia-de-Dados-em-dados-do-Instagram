"""Testes de `UGCMentionCleaner` (ADR 0020, Ficha 8 / issue #93)."""

import json

import pandas as pd

from src.delta_io import conform_to_schema
from src.features.silver.ugc_mention_cleaner import UGCMentionCleaner
from src.schemas_delta import SILVER_UGC_MENTIONS_SCHEMA


def _bronze_row(**overrides) -> dict:
    row = {
        "id": "m1",
        "shortCode": "abc123",
        "type": "Image",
        "caption": "que orgulho do governador!",
        "mentions": json.dumps(["governador_x"]),
        "matchTypes": json.dumps(["mentioned"]),
        "likesCount": 10,
        "commentsCount": 2,
        "videoPlayCount": None,
        "timestamp": "2026-05-01T00:00:00+00:00",
        "authorUsername": None,
        "ownerUsername": "eleitor_1",
        "authorIsVerified": False,
        "isPaidPartnership": False,
        "isAd": False,
        "isAffiliate": False,
        "_ingested_at": pd.Timestamp("2026-05-01", tz="UTC"),
        "_run_id": "r1",
        "_source": "apify",
    }
    row.update(overrides)
    return row


def test_dedup_por_id():
    df = pd.DataFrame(
        [
            _bronze_row(id="m1", _run_id="r1", _ingested_at=pd.Timestamp("2026-05-01", tz="UTC")),
            _bronze_row(id="m1", _run_id="r2", _ingested_at=pd.Timestamp("2026-05-02", tz="UTC")),
        ]
    )
    out = UGCMentionCleaner().clean(df, run_id="r2")
    assert len(out) == 1
    assert out.iloc[0]["_run_id"] == "r2"


def test_dedup_por_short_code_quando_id_ausente():
    """Issue #93: dedup por id/shortCode -- quando `id` falta em uma
    execução mas `shortCode` é o mesmo, ainda precisa deduplicar."""
    df = pd.DataFrame(
        [
            _bronze_row(id=None, shortCode="abc123", _run_id="r1", _ingested_at=pd.Timestamp("2026-05-01", tz="UTC")),
            _bronze_row(id=None, shortCode="abc123", _run_id="r2", _ingested_at=pd.Timestamp("2026-05-02", tz="UTC")),
        ]
    )
    out = UGCMentionCleaner().clean(df, run_id="r2")
    assert len(out) == 1
    assert out.iloc[0]["_run_id"] == "r2"


def test_descarta_linha_sem_id_e_sem_short_code():
    df = pd.DataFrame(
        [
            _bronze_row(id=None, shortCode=None),
            _bronze_row(id="m2", shortCode="def456"),
        ]
    )
    out = UGCMentionCleaner().clean(df, run_id="r1")
    assert len(out) == 1
    assert out.iloc[0]["id"] == "m2"


def test_normaliza_handle_de_autor_preferindo_author_username():
    df = pd.DataFrame([_bronze_row(authorUsername="eleitor_confirmado", ownerUsername="eleitor_1")])
    out = UGCMentionCleaner().clean(df, run_id="r1")
    assert out.iloc[0]["authorUsername"] == "eleitor_confirmado"


def test_normaliza_handle_de_autor_cai_para_owner_username():
    df = pd.DataFrame([_bronze_row(authorUsername=None, ownerUsername="eleitor_1")])
    out = UGCMentionCleaner().clean(df, run_id="r1")
    assert out.iloc[0]["authorUsername"] == "eleitor_1"


def test_normalizacao_de_handle_nao_quebra_com_ambos_ausentes():
    df = pd.DataFrame([_bronze_row(authorUsername=None, ownerUsername=None)])
    out = UGCMentionCleaner().clean(df, run_id="r1")
    assert pd.isna(out.iloc[0]["authorUsername"])


def test_resolve_governor_username_a_partir_de_mentions():
    df = pd.DataFrame([_bronze_row(mentions=json.dumps(["governador_x", "outro_perfil"]))])
    out = UGCMentionCleaner().clean(df, run_id="r1", governor_usernames=["governador_x", "governador_y"])
    assert out.iloc[0]["governor_username"] == "governador_x"


def test_governor_username_nulo_quando_mentions_nao_bate_com_conhecidos():
    df = pd.DataFrame([_bronze_row(mentions=json.dumps(["perfil_desconhecido"]))])
    out = UGCMentionCleaner().clean(df, run_id="r1", governor_usernames=["governador_x"])
    assert pd.isna(out.iloc[0]["governor_username"])


def test_governor_username_nulo_quando_mentions_ausente():
    df = pd.DataFrame([_bronze_row()]).drop(columns=["mentions"])
    out = UGCMentionCleaner().clean(df, run_id="r1", governor_usernames=["governador_x"])
    assert pd.isna(out.iloc[0]["governor_username"])


def test_governor_username_nulo_quando_mentions_e_json_invalido():
    df = pd.DataFrame([_bronze_row(mentions="{nao e json valido")])
    out = UGCMentionCleaner().clean(df, run_id="r1", governor_usernames=["governador_x"])
    assert pd.isna(out.iloc[0]["governor_username"])


def test_flags_de_publi_default_para_false_quando_ausentes():
    """Ausência da flag não pode quebrar -- default orgânico (False), mesmo
    padrão de `ProfileCleaner.BOOL_COLUMNS`."""
    row = _bronze_row()
    del row["isPaidPartnership"], row["isAd"], row["isAffiliate"]
    df = pd.DataFrame([row])
    out = UGCMentionCleaner().clean(df, run_id="r1")
    assert bool(out.iloc[0]["isPaidPartnership"]) is False
    assert bool(out.iloc[0]["isAd"]) is False
    assert bool(out.iloc[0]["isAffiliate"]) is False


def test_flags_de_publi_preservam_true():
    df = pd.DataFrame([_bronze_row(isPaidPartnership=True)])
    out = UGCMentionCleaner().clean(df, run_id="r1")
    assert bool(out.iloc[0]["isPaidPartnership"]) is True


def test_parseia_timestamp_para_data_hora():
    df = pd.DataFrame([_bronze_row(timestamp="2026-05-01T00:00:00+00:00")])
    out = UGCMentionCleaner().clean(df, run_id="r1")
    assert out["data_hora"].notna().all()


def test_conforma_ao_contrato_silver():
    df = pd.DataFrame([_bronze_row(), _bronze_row(id="m2", shortCode="def456")])
    out = UGCMentionCleaner().clean(df, run_id="r1", governor_usernames=["governador_x"])
    table = conform_to_schema(out, SILVER_UGC_MENTIONS_SCHEMA)
    assert table.num_rows == 2


def test_video_play_count_nulo_nao_vira_zero():
    df = pd.DataFrame([_bronze_row(videoPlayCount=None)])
    out = UGCMentionCleaner().clean(df, run_id="r1")
    assert pd.isna(out.iloc[0]["videoPlayCount"])
