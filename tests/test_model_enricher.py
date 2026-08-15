import pandas as pd
import pytest
from deltalake import DeltaTable

from src.features.gold.model_enricher import ModelEnricher


def _comentarios_com_sentimento():
    return pd.DataFrame(
        {
            "id_reel": ["r1"],
            "id_comment": ["c1"],
            "text": ["ótimo trabalho"],
            "ownerUsername": ["eleitor"],
            "sentiment_label": ["Positive"],
            "sentiment_score": [0.95],
            "Topic": [3],
            "Name": ["3_saude_hospital"],
        }
    )


def _reels_clusterizados():
    # Colunas produzidas pelo notebook 03 após AutoClusterHPO.fit_predict:
    # 'Clusters (AutoClusterHPO)', 'algo_name' e 'score' vêm de um único
    # modelo vencedor, por isso são constantes entre as linhas.
    return pd.DataFrame(
        {
            "id": ["r1", "r2"],
            "ownerUsername": ["governador_a", "governador_b"],
            "Clusters (AutoClusterHPO)": [0, -1],
            "algo_name": ["DBSCAN", "DBSCAN"],
            "score": [0.62, 0.62],
        }
    )


def test_write_sentiment_grava_topico_junto_do_sentimento(tmp_path):
    path = tmp_path / "governor_sentiment"
    ModelEnricher().write_sentiment(_comentarios_com_sentimento(), path, run_id="r1")

    out = DeltaTable(str(path)).to_pandas()
    assert len(out) == 1
    assert out.loc[0, "sentiment_label"] == "Positive"
    assert out.loc[0, "Topic"] == 3


def test_write_clusters_usa_granularidade_de_reel(tmp_path):
    """
    A clusterização do AutoClusterHPO é por reel (PCA de engajamento/duração
    do vídeo), não por perfil — não há clusterização de governadores no
    projeto. O schema e a escrita precisam refletir isso.
    """
    path = tmp_path / "governor_clusters"
    ModelEnricher().write_clusters(_reels_clusterizados(), path, run_id="r1")

    out = DeltaTable(str(path)).to_pandas()
    assert len(out) == 2
    assert set(out.columns) >= {"id_reel", "ownerUsername", "cluster_label"}
    assert out.loc[out["id_reel"] == "r2", "cluster_label"].iloc[0] == -1


def test_write_clusters_falha_com_mensagem_clara_se_faltar_coluna(tmp_path):
    df_incompleto = _reels_clusterizados().drop(columns=["algo_name"])

    with pytest.raises(ValueError, match="algo_name"):
        ModelEnricher().write_clusters(df_incompleto, tmp_path / "governor_clusters", run_id="r1")
