from datetime import datetime, timezone

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


def _legenda_com_sentimento():
    return pd.DataFrame(
        {
            "id_reel": ["p1"],
            "text": ["Anunciamos hoje um novo investimento em saúde para todo o estado."],
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "ownerUsername": ["governador_a"],
            "sentiment_label": ["Positive"],
            "sentiment_score": [0.81],
        }
    )


def _transcricao_com_sentimento():
    return pd.DataFrame(
        {
            "id_reel": ["r9"],
            "text": ["Estamos trabalhando para melhorar a saúde da nossa população."],
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "ownerUsername": ["governador_a"],
            "sentiment_label": ["Positive"],
            "sentiment_score": [0.77],
        }
    )


def test_write_sentiment_grava_topico_junto_do_sentimento(tmp_path):
    path = tmp_path / "governor_sentiment"
    ModelEnricher().write_sentiment(_comentarios_com_sentimento(), path, run_id="r1")

    out = DeltaTable(str(path)).to_pandas()
    assert len(out) == 1
    assert out.loc[0, "sentiment_label"] == "Positive"
    assert out.loc[0, "Topic"] == 3


def test_write_sentiment_usa_fonte_comentario_por_padrao(tmp_path):
    """Comportamento pré-existente: quem já chama `write_sentiment` sem
    informar `fonte` (todos os call sites de `orchestration.py` para
    comentários) continua gravando "comentario", sem precisar mudar
    nenhuma chamada existente (ADR 0020 Ficha 3 / issue #88)."""
    path = tmp_path / "governor_sentiment"
    ModelEnricher().write_sentiment(_comentarios_com_sentimento(), path, run_id="r1")

    out = DeltaTable(str(path)).to_pandas()
    assert out.loc[0, "fonte"] == "comentario"


def test_write_sentiment_grava_fonte_legenda(tmp_path):
    path = tmp_path / "governor_sentiment"
    ModelEnricher().write_sentiment(_legenda_com_sentimento(), path, run_id="r1", fonte="legenda")

    out = DeltaTable(str(path)).to_pandas()
    assert len(out) == 1
    assert out.loc[0, "fonte"] == "legenda"
    assert out.loc[0, "sentiment_label"] == "Positive"


def test_write_sentiment_grava_fonte_transcricao(tmp_path):
    path = tmp_path / "governor_sentiment"
    ModelEnricher().write_sentiment(
        _transcricao_com_sentimento(), path, run_id="r1", fonte="transcricao"
    )

    out = DeltaTable(str(path)).to_pandas()
    assert len(out) == 1
    assert out.loc[0, "fonte"] == "transcricao"


def test_write_sentiment_tres_fontes_coexistem_sem_colidir(tmp_path):
    """`governor_sentiment` acumula comentário/legenda/transcrição na mesma
    tabela (ADR 0020 Ficha 3 / issue #88) -- a primeira escrita usa o modo
    default (overwrite), as seguintes precisam de `mode="append"` para não
    apagar as fontes já gravadas."""
    path = tmp_path / "governor_sentiment"
    enricher = ModelEnricher()

    enricher.write_sentiment(_comentarios_com_sentimento(), path, run_id="r1")
    enricher.write_sentiment(
        _legenda_com_sentimento(), path, run_id="r1", mode="append", fonte="legenda"
    )
    enricher.write_sentiment(
        _transcricao_com_sentimento(), path, run_id="r1", mode="append", fonte="transcricao"
    )

    out = DeltaTable(str(path)).to_pandas()
    assert len(out) == 3
    assert set(out["fonte"]) == {"comentario", "legenda", "transcricao"}
    # Cada fonte preserva seu próprio texto e sentimento -- nenhuma
    # sobrescreveu a linha da outra.
    por_fonte = out.set_index("fonte")
    assert por_fonte.loc["comentario", "text"] == "ótimo trabalho"
    assert por_fonte.loc["legenda", "id_reel"] == "p1"
    assert por_fonte.loc["transcricao", "id_reel"] == "r9"


def test_write_sentiment_repassa_mode_para_write_delta(monkeypatch):
    """`governor_sentiment_history` (issue #52) depende de `write_sentiment`
    repassar `mode` para `write_delta` -- sem isso, toda escrita seria
    sempre overwrite, e o histórico nunca acumularia mais de uma linha por
    execução de modelagem (mesmo raciocínio do PR #49 para engajamento)."""
    captured = {}

    def fake_write_delta(path, df, schema, mode="overwrite"):
        captured["path"] = path
        captured["mode"] = mode

    monkeypatch.setattr("src.features.gold.model_enricher.write_delta", fake_write_delta)

    ModelEnricher().write_sentiment(
        _comentarios_com_sentimento(), "some/path", run_id="r1", mode="append"
    )

    assert captured["mode"] == "append"


def test_write_sentiment_aceita_generated_at_explicito_para_manter_consistencia(tmp_path):
    """`governor_sentiment` e `governor_sentiment_history` (issue #52) são
    escritos em duas chamadas separadas para o mesmo run -- sem um
    `generated_at` explícito compartilhado, cada chamada carimbaria
    `datetime.now()` na hora em que rodou, fazendo as duas tabelas
    registrarem timestamps ligeiramente diferentes para a mesma execução
    (como se fossem gerações distintas). Mesmo raciocínio de
    `EngagementAggregator.aggregate()`, que carimba `_generated_at` uma
    única vez antes de qualquer escrita."""
    generated_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    path_a = tmp_path / "governor_sentiment"
    path_b = tmp_path / "governor_sentiment_history"

    ModelEnricher().write_sentiment(
        _comentarios_com_sentimento(), path_a, run_id="r1", generated_at=generated_at
    )
    ModelEnricher().write_sentiment(
        _comentarios_com_sentimento(),
        path_b,
        run_id="r1",
        mode="append",
        generated_at=generated_at,
    )

    out_a = DeltaTable(str(path_a)).to_pandas()
    out_b = DeltaTable(str(path_b)).to_pandas()
    assert out_a.loc[0, "_generated_at"] == out_b.loc[0, "_generated_at"] == generated_at


def test_write_clusters_usa_granularidade_de_reel(tmp_path):
    """
    `write_clusters` é especificamente para a clusterização de reel do
    AutoClusterHPO (PCA de engajamento/duração do vídeo) -- granularidade
    de reel, não de perfil de governador (essa é `write_profile_clusters_engagement`,
    ver testes abaixo). O schema e a escrita precisam refletir isso.
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


def _perfis_clusterizados():
    # Colunas produzidas por cluster_governor_profiles/run_autocluster:
    # 'Clusters (AutoClusterHPO)', 'algo_name' e 'score' vêm de um único
    # modelo vencedor, por isso são constantes entre as linhas.
    return pd.DataFrame(
        {
            "inputUrl": [
                "https://www.instagram.com/governador_a/",
                "https://www.instagram.com/governador_b/",
            ],
            "Clusters (AutoClusterHPO)": [0, -1],
            "algo_name": ["KMeans", "KMeans"],
            "score": [0.55, 0.55],
        }
    )


def test_write_profile_clusters_engagement_usa_granularidade_de_perfil(tmp_path):
    """
    Fase 2: clusterização de PERFIL de governador por Engajamento -- 1 linha
    por governador (`inputUrl`), diferente de `write_clusters` (1 linha por
    reel). Tabela/schema separados de propósito, ver ADR 0004/0005.
    """
    path = tmp_path / "governor_profile_clusters_engagement"
    ModelEnricher().write_profile_clusters_engagement(_perfis_clusterizados(), path, run_id="r1")

    out = DeltaTable(str(path)).to_pandas()
    assert len(out) == 2
    assert set(out.columns) >= {"inputUrl", "cluster_label"}
    assert out.loc[
        out["inputUrl"] == "https://www.instagram.com/governador_b/", "cluster_label"
    ].iloc[0] == -1


def test_write_profile_clusters_engagement_falha_com_mensagem_clara_se_faltar_coluna(tmp_path):
    df_incompleto = _perfis_clusterizados().drop(columns=["algo_name"])

    with pytest.raises(ValueError, match="algo_name"):
        ModelEnricher().write_profile_clusters_engagement(
            df_incompleto, tmp_path / "governor_profile_clusters_engagement", run_id="r1"
        )
