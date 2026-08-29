import pandas as pd

from src.features.silver.comment_cleaner import CommentCleaner
from src.features.silver.post_cleaner import PostCleaner
from src.features.silver.profile_cleaner import ProfileCleaner


def test_profile_cleaner_basic():
    df = pd.DataFrame(
        {
            "id": ["1"],
            "username": ["g"],
            "followersCount": [100],
            "_ingested_at": pd.to_datetime(["2026-05-01"], utc=True),
            "_run_id": ["r1"],
        }
    )
    cleaner = ProfileCleaner()
    out = cleaner.clean(df, run_id="r1")
    assert "_source_layer" in out.columns


def test_profile_cleaner_adds_fullname_when_missing():
    df = pd.DataFrame(
        {
            "id": ["1"],
            "username": ["g"],
            "followersCount": [100],
            "_ingested_at": pd.to_datetime(["2026-05-01"], utc=True),
            "_run_id": ["r1"],
        }
    )
    cleaner = ProfileCleaner()
    out = cleaner.clean(df, run_id="r1")
    assert "fullName" in out.columns
    assert out.loc[0, "fullName"] == "g"


def test_profile_cleaner_descarta_linhas_com_id_nulo():
    """
    A Apify ocasionalmente retorna um resultado de scrape sem `id` (perfil
    indisponível/erro parcial). SILVER_PROFILES_SCHEMA exige `id` não nulo --
    sem descartar essas linhas, a escrita da Silver inteira quebraria.
    """
    df = pd.DataFrame(
        {
            "id": ["1", None],
            "username": ["g", "sem_id"],
            "followersCount": [100, 50],
            "_ingested_at": pd.to_datetime(["2026-05-01", "2026-05-01"], utc=True),
            "_run_id": ["r1", "r1"],
        }
    )
    cleaner = ProfileCleaner()
    out = cleaner.clean(df, run_id="r1")
    assert len(out) == 1
    assert out.iloc[0]["id"] == "1"


def test_post_cleaner_feed_and_reel():
    df_posts = pd.DataFrame(
        {
            "id": ["p1"],
            "ownerId": ["1"],
            "ownerUsername": ["g"],
            "commentsCount": [1],
            "likesCount": [2],
            "timestamp": ["2026-05-01T00:00:00+00:00"],
            "_ingested_at": pd.to_datetime(["2026-05-01"], utc=True),
            "_run_id": ["r1"],
        }
    )
    pc = PostCleaner()
    outp = pc.clean_posts(df_posts)
    assert (outp["Tipo"] == "FEED").all()

    df_reels = pd.DataFrame(
        {
            "id": ["r1"],
            "ownerId": ["1"],
            "ownerUsername": ["g"],
            "commentsCount": [1],
            "likesCount": [2],
            "timestamp": ["2026-05-01T00:00:00+00:00"],
            "latestComments": ["[]"],
            "_ingested_at": pd.to_datetime(["2026-05-01"], utc=True),
            "_run_id": ["r1"],
        }
    )
    outr = pc.clean_reels(df_reels)
    assert (outr["Tipo"] == "REELS").all()


def test_comment_cleaner_explode():
    df_reels = pd.DataFrame(
        {"id": ["r1"], "latestComments": ['[{"id": "c1", "text": "ok"}]']}
    )
    cc = CommentCleaner()
    out = cc.clean(df_reels)
    assert not out.empty


def test_post_cleaner_deduplica_execucoes_acumuladas():
    """
    A Bronze é append-only. Sem deduplicação, reprocessar o pipeline
    multiplicaria as publicações e inflaria as métricas da camada Gold.
    """
    linha = {
        "id": "p1",
        "ownerId": "1",
        "ownerUsername": "g",
        "commentsCount": 1,
        "likesCount": 2,
        "timestamp": "2026-05-01T00:00:00+00:00",
        "_run_id": "r1",
    }
    df = pd.DataFrame([linha, {**linha, "_run_id": "r2"}])
    df["_ingested_at"] = pd.to_datetime(["2026-05-01", "2026-05-02"], utc=True)

    out = PostCleaner().clean_posts(df)

    assert len(out) == 1
    # Mantém a ingestão mais recente
    assert out.iloc[0]["_run_id"] == "r2"


def test_comment_cleaner_promove_colunas_do_comentario():
    """
    O join reel × comentário sufixa colunas homônimas. Os campos que
    descrevem o comentário precisam chegar ao Silver sem sufixo, como
    SILVER_COMMENTS_SCHEMA declara.
    """
    df_reels = pd.DataFrame(
        {
            "id": ["r1"],
            "ownerUsername": ["governador"],
            "likesCount": [500],
            "timestamp": ["2026-05-01T00:00:00+00:00"],
            "latestComments": [
                (
                    '[{"id": "c1", "text": "ok", "ownerUsername": "eleitor",'
                    ' "likesCount": 3, "timestamp": "2026-05-02T00:00:00+00:00"}]'
                )
            ],
        }
    )

    out = CommentCleaner().clean(df_reels)

    assert out.iloc[0]["ownerUsername"] == "eleitor"
    assert out.iloc[0]["likesCount"] == 3
    assert out.iloc[0]["timestamp"].startswith("2026-05-02")


def test_comment_cleaner_deduplica_execucoes_acumuladas():
    """
    Assim como a Bronze de posts/reels, o mesmo comentário reaparece a cada
    reprocessamento do pipeline (o reel é reingerido inteiro, com
    latestComments embutido). Sem deduplicar por id_comment, comentários se
    acumulariam a cada execução.
    """
    comment = '[{"id": "c1", "text": "ok", "ownerUsername": "eleitor"}]'
    df_reels = pd.DataFrame(
        {
            "id": ["r1", "r1"],
            "ownerUsername": ["governador", "governador"],
            "latestComments": [comment, comment],
            "_ingested_at": pd.to_datetime(["2026-05-01", "2026-05-02"], utc=True),
            "_run_id": ["r1_run", "r2_run"],
        }
    )

    out = CommentCleaner().clean(df_reels)

    assert len(out) == 1
    assert out.iloc[0]["_run_id"] == "r2_run"
