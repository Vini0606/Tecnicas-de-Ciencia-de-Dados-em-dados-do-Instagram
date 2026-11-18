"""`derivar_silver_gold` ponta a ponta (ADR 0046 / issue #314): a Bronze é
escrita pelo `BronzeWriter` e lida pelo `DeltaRepository`; Silver e Gold saem
nos caminhos de destino. Sem rede, sem Apify."""

from deltalake import DeltaTable

from src.coleta.derivacao import caminhos_do_destino, derivar_silver_gold, repositorio_do_destino
from src.data_extract.bronze_writer import BronzeWriter
from test_coleta_coletar import LINK, _post, _reel

GOV = ["gov_a"]


def _perfil():
    return {
        "id": "1",
        "username": "gov_a",
        "fullName": "Governador A",
        "inputUrl": LINK,
        "followersCount": 1000,
        "followsCount": 10,
        "postsCount": 50,
    }


def _ugc(id_="u1"):
    return {
        "id": id_,
        "shortCode": f"sc_{id_}",
        "timestamp": "2026-08-15T10:00:00.000Z",
        "ownerUsername": "eleitor_1",
        "taggedUsers": [{"username": "gov_a"}],
        "mentions": [],
        "likesCount": 3,
        "commentsCount": 1,
        "paidPartnership": False,
    }


def _escrever_bronze(destino, com_ugc=True):
    p = caminhos_do_destino(destino)
    writer = BronzeWriter(
        p["bronze_profiles"],
        p["bronze_posts"],
        p["bronze_reels"],
        bronze_ugc_mentions_path=p["bronze_ugc"],
    )
    writer.write_profiles([_perfil()], run_id="run_b")
    writer.write_posts([_post("p1", "2026-08-10T10:00:00.000Z")], run_id="run_b")
    writer.write_reels([_reel("r1", "2026-08-12T10:00:00.000Z")], run_id="run_b")
    if com_ugc:
        writer.write_ugc_mentions([_ugc()], run_id="run_b")
    return p


def _linhas(caminho) -> int:
    return len(DeltaTable(str(caminho)).to_pandas())


def test_derivacao_le_a_bronze_pelo_repositorio_e_grava_silver_e_gold(tmp_path):
    p = _escrever_bronze(tmp_path)

    gold = derivar_silver_gold(repositorio_do_destino(p), p, GOV, run_id="run_d")

    assert gold["username"].tolist() == ["gov_a"]
    assert {"TOTAL ENGAJAMENTO", "% ENGAJAMENTO", "RECENCIA", "FREQUENCIA"} <= set(gold.columns)
    for chave in (
        "silver_profiles",
        "silver_posts",
        "silver_reels",
        "silver_comments",
        "silver_ugc",
        "gold_engagement",
        "gold_engagement_history",
        "gold_ugc",
    ):
        assert _linhas(p[chave]) >= 1, chave
    # governors_metadata vem da planilha, nao da derivacao
    assert not (tmp_path / "silver" / "governors_metadata").exists()


def test_derivacao_sem_bronze_de_ugc_segue_e_nao_cria_ugc(tmp_path):
    p = _escrever_bronze(tmp_path, com_ugc=False)

    derivar_silver_gold(repositorio_do_destino(p), p, GOV, run_id="run_d")

    assert _linhas(p["gold_engagement"]) == 1
    assert not (tmp_path / "silver" / "ugc_mentions").exists()
    assert not (tmp_path / "gold" / "governor_ugc_mentions").exists()


def test_leitura_e_escrita_podem_apontar_para_lugares_diferentes(tmp_path):
    """Caso da reconstrucao: le a Bronze do Snapshot, grava Silver/Gold noutro destino."""
    origem = _escrever_bronze(tmp_path / "snapshot")
    destino = caminhos_do_destino(tmp_path / "s3_simulado")

    derivar_silver_gold(repositorio_do_destino(origem), destino, GOV, run_id="run_d")

    assert _linhas(destino["gold_engagement"]) == 1
    assert not (tmp_path / "snapshot" / "gold").exists()


def test_modo_historico_overwrite_nao_acumula_e_append_acumula(tmp_path):
    p = _escrever_bronze(tmp_path)
    repo = repositorio_do_destino(p)

    derivar_silver_gold(repo, p, GOV, run_id="r1", modo_historico="overwrite")
    derivar_silver_gold(repo, p, GOV, run_id="r2", modo_historico="overwrite")
    assert _linhas(p["gold_engagement_history"]) == 1

    derivar_silver_gold(repo, p, GOV, run_id="r3", modo_historico="append")
    assert _linhas(p["gold_engagement_history"]) == 2
