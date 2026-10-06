"""Issue #212: comentários de posts de feed -- Bronze guarda `latestComments`,
Silver separada (`post_comments_clean`) e combinação com os comentários de
reels na modelagem, com a origem preservada em `origem_comentario`."""

import pandas as pd
import pyarrow as pa
import pytest
from deltalake import DeltaTable, write_deltalake

from src.data_extract.bronze_writer import BronzeWriter
from src.features.gold.model_enricher import ModelEnricher
from src.features.silver.comment_cleaner import CommentCleaner
from src.modeling.comment_sources import combine_comment_sources
from src.schemas_delta import BRONZE_POSTS_SCHEMA


def _comentario(id_comment, text="ok", autor="eleitor"):
    return f'{{"id": "{id_comment}", "text": "{text}", "ownerUsername": "{autor}"}}'


def test_bronze_de_posts_guarda_latest_comments_como_json(tmp_path):
    writer = BronzeWriter(tmp_path / "profiles", tmp_path / "posts", tmp_path / "reels")

    writer.write_posts(
        [{"id": "p1", "latestComments": [{"id": "c1", "text": "ok"}]}], run_id="run_1"
    )

    out = writer.get_latest_posts()
    assert out.iloc[0]["latestComments"] == '[{"id": "c1", "text": "ok"}]'


def test_bronze_de_posts_antiga_sem_latest_comments_aceita_append(tmp_path):
    """Bronze de posts gravada antes da #212 (sem a coluna) recebe a coluna
    nova no append, sem migração; linhas antigas ficam nulas."""
    schema_antigo = pa.schema([f for f in BRONZE_POSTS_SCHEMA if f.name != "latestComments"])
    antiga = pd.DataFrame(
        {
            "id": ["p0"],
            "_ingested_at": pd.to_datetime(["2026-09-01"], utc=True),
            "_run_id": ["run_0"],
            "_source": ["apify"],
        }
    )
    for field in schema_antigo:
        if field.name not in antiga.columns:
            antiga[field.name] = pd.NA
    write_deltalake(
        str(tmp_path / "posts"),
        pa.Table.from_pandas(antiga, schema=schema_antigo, preserve_index=False),
    )
    writer = BronzeWriter(tmp_path / "profiles", tmp_path / "posts", tmp_path / "reels")

    writer.write_posts([{"id": "p1", "latestComments": [{"id": "c1"}]}], run_id="run_1")

    out = writer.get_latest_posts().set_index("id")
    assert pd.isna(out.loc["p0", "latestComments"])
    assert out.loc["p1", "latestComments"] == '[{"id": "c1"}]'


def test_comment_cleaner_de_posts_gera_id_post_e_filtra_governador_antes_do_explode():
    df_posts = pd.DataFrame(
        {
            "id": ["p1", "p2"],
            "ownerUsername": ["governador_atual", "governador_removido"],
            "latestComments": [f"[{_comentario('c1')}]", f"[{_comentario('c2')}]"],
        }
    )

    out = CommentCleaner(origem="post").clean(df_posts, governor_usernames=["governador_atual"])

    assert list(out["id_comment"]) == ["c1"]
    assert out.iloc[0]["id_post"] == "p1"
    assert "id_reel" not in out.columns
    assert out.iloc[0]["ownerUsername"] == "eleitor"


def test_comment_cleaner_de_posts_descarta_texto_com_512_caracteres_ou_mais():
    df_posts = pd.DataFrame(
        {
            "id": ["p1"],
            "latestComments": [
                f"[{_comentario('c_curto', 'a' * 511)}, {_comentario('c_longo', 'a' * 512)}]"
            ],
        }
    )

    out = CommentCleaner(origem="post").clean(df_posts)

    assert list(out["id_comment"]) == ["c_curto"]


def test_comment_cleaner_de_posts_grava_tabela_silver_com_id_post(tmp_path):
    df_posts = pd.DataFrame({"id": ["p1"], "latestComments": [f"[{_comentario('c1')}]"]})
    cleaner = CommentCleaner(origem="post")
    df = cleaner.clean(df_posts)
    df["_ingested_at"] = pd.Timestamp("2026-10-01", tz="UTC")
    df["_run_id"] = "run_1"

    cleaner.write(df, tmp_path / "post_comments_clean")

    gravado = DeltaTable(str(tmp_path / "post_comments_clean")).to_pandas()
    assert gravado.iloc[0]["id_post"] == "p1"
    assert "id_reel" not in gravado.columns


def test_comment_cleaner_rejeita_origem_desconhecida():
    with pytest.raises(ValueError, match="origem"):
        CommentCleaner(origem="story")


def _reel_comments():
    return pd.DataFrame(
        {"id_reel": ["r1", "r1"], "id_comment": ["c1", "c2"], "text": ["a", "b"]}
    )


def _post_comments():
    # c2 é o mesmo comentário de r1 visto pelo scraper de posts (o reel também
    # aparece no grid de posts); c3 é comentário de um post de feed.
    return pd.DataFrame(
        {"id_post": ["r1", "p9"], "id_comment": ["c2", "c3"], "text": ["b", "c"]}
    )


def test_combine_comment_sources_marca_origem_e_unifica_id_da_publicacao():
    out = combine_comment_sources(_reel_comments(), _post_comments()).set_index("id_comment")

    assert out.loc["c1", "origem_comentario"] == "reel"
    assert out.loc["c3", "origem_comentario"] == "post"
    assert out.loc["c3", "id_reel"] == "p9"
    assert "id_post" not in out.columns


def test_combine_comment_sources_deduplica_por_id_comment_preferindo_reel():
    out = combine_comment_sources(_reel_comments(), _post_comments())

    assert sorted(out["id_comment"]) == ["c1", "c2", "c3"]
    assert out.set_index("id_comment").loc["c2", "origem_comentario"] == "reel"


def test_combine_comment_sources_loga_contagens(caplog):
    with caplog.at_level("INFO"):
        combine_comment_sources(_reel_comments(), _post_comments())

    assert "reels=2 posts=2 duplicados=1 total=3" in caplog.text


@pytest.mark.parametrize("df_posts", [None, pd.DataFrame()], ids=["none", "vazio"])
def test_combine_comment_sources_sem_comentarios_de_posts_mantem_so_reels(df_posts):
    out = combine_comment_sources(_reel_comments(), df_posts)

    assert list(out["id_comment"]) == ["c1", "c2"]
    assert (out["origem_comentario"] == "reel").all()


def test_write_sentiment_grava_origem_e_deixa_nula_em_legenda(tmp_path):
    path = tmp_path / "governor_sentiment"
    enricher = ModelEnricher()
    comentarios = combine_comment_sources(_reel_comments(), _post_comments())
    enricher.write_sentiment(comentarios, path, "run_1")
    legendas = pd.DataFrame({"id_reel": ["p9"], "text": ["legenda"]})
    enricher.write_sentiment(legendas, path, "run_1", mode="append", fonte="legenda")

    out = DeltaTable(str(path)).to_pandas()

    origem_por_fonte = out.groupby("fonte")["origem_comentario"].apply(set).to_dict()
    assert origem_por_fonte["comentario"] == {"reel", "post"}
    assert out.loc[out["fonte"] == "legenda", "origem_comentario"].isna().all()
