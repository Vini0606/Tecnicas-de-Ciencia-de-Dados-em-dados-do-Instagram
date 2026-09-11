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
    # modelo vencedor, por isso são constantes entre as linhas. `content_type`
    # (ADR 0020, Ficha 2 / issue #87) é a coluna discriminadora que
    # `write_clusters` passou a exigir.
    return pd.DataFrame(
        {
            "id": ["r1", "r2"],
            "ownerUsername": ["governador_a", "governador_b"],
            "Clusters (AutoClusterHPO)": [0, -1],
            "algo_name": ["DBSCAN", "DBSCAN"],
            "score": [0.62, 0.62],
            "content_type": ["reel", "reel"],
        }
    )


def _feed_clusterizados():
    # Mesma forma de `_reels_clusterizados`, granularidade de post de feed
    # (ADR 0020, Ficha 2 / issue #87) -- ids deliberadamente distintos dos de
    # `_reels_clusterizados` para o teste de escrita combinada confirmar que
    # as duas granularidades coexistem sem colidir.
    return pd.DataFrame(
        {
            "id": ["p1", "p2"],
            "ownerUsername": ["governador_a", "governador_b"],
            "Clusters (AutoClusterHPO)": [1, 0],
            "algo_name": ["KMeans", "KMeans"],
            "score": [0.71, 0.71],
            "content_type": ["feed", "feed"],
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


def _discurso_legenda():
    return pd.DataFrame(
        {
            "id_reel": ["p1"],
            "text": ["Anunciamos hoje um novo investimento em saúde para todo o estado."],
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "ownerUsername": ["governador_a"],
            "fonte": ["legenda"],
            "Topic": [2],
            "Name": ["2_saude_investimento"],
        }
    )


def _discurso_transcricao():
    return pd.DataFrame(
        {
            "id_reel": ["r9"],
            "text": ["Estamos trabalhando para melhorar a saúde da nossa população."],
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "ownerUsername": ["governador_a"],
            "fonte": ["transcricao"],
            "Topic": [2],
            "Name": ["2_saude_investimento"],
        }
    )


def test_write_discourse_topics_grava_topico_de_discurso(tmp_path):
    """ADR 0020 (Ficha 4) / issue #89."""
    path = tmp_path / "governor_discourse_topics"
    ModelEnricher().write_discourse_topics(_discurso_legenda(), path, run_id="r1")

    out = DeltaTable(str(path)).to_pandas()
    assert len(out) == 1
    assert out.loc[0, "fonte"] == "legenda"
    assert out.loc[0, "Topic"] == 2
    assert out.loc[0, "Name"] == "2_saude_investimento"


def test_write_discourse_topics_duas_fontes_coexistem_na_mesma_escrita(tmp_path):
    """Legenda e transcrição são modeladas juntas (mesmo corpus/modelo, ver
    `run_deterministic_modeling`) -- uma única escrita grava as duas fontes
    lado a lado, ao contrário de `write_sentiment` (uma chamada em
    `mode="append"` por fonte)."""
    path = tmp_path / "governor_discourse_topics"
    df_combinado = pd.concat([_discurso_legenda(), _discurso_transcricao()], ignore_index=True)

    ModelEnricher().write_discourse_topics(df_combinado, path, run_id="r1")

    out = DeltaTable(str(path)).to_pandas()
    assert len(out) == 2
    assert set(out["fonte"]) == {"legenda", "transcricao"}


def test_write_discourse_topics_falha_com_mensagem_clara_se_faltar_fonte(tmp_path):
    df_incompleto = _discurso_legenda().drop(columns=["fonte"])

    with pytest.raises(ValueError, match="fonte"):
        ModelEnricher().write_discourse_topics(
            df_incompleto, tmp_path / "governor_discourse_topics", run_id="r1"
        )


def test_write_discourse_topics_nao_grava_colunas_de_sentimento(tmp_path):
    """Tabela própria (ADR 0020 Ficha 4 / issue #89), não uma extensão de
    `governor_sentiment`: mesmo que o DataFrame de origem carregue
    `sentiment_label`/`sentiment_score` (reaproveita o mesmo
    df_fonte_sentiment da etapa de sentimento, ver `run_deterministic_modeling`),
    essas colunas não pertencem ao contrato de `governor_discourse_topics` e
    não podem vazar pra ela."""
    path = tmp_path / "governor_discourse_topics"
    df_com_sentimento = _discurso_legenda().assign(
        sentiment_label="Positive", sentiment_score=0.81
    )

    ModelEnricher().write_discourse_topics(df_com_sentimento, path, run_id="r1")

    out = DeltaTable(str(path)).to_pandas()
    assert "sentiment_label" not in out.columns
    assert "sentiment_score" not in out.columns


def test_write_clusters_usa_granularidade_de_reel(tmp_path):
    """
    `write_clusters` grava clusters de granularidade de post (reel ou feed,
    ver `content_type` -- ADR 0020, Ficha 2 / issue #87) do AutoClusterHPO
    (PCA de engajamento) -- não de perfil de governador (essa é
    `write_profile_clusters_engagement`, ver testes abaixo). O schema e a
    escrita precisam refletir isso.
    """
    path = tmp_path / "governor_clusters"
    ModelEnricher().write_clusters(_reels_clusterizados(), path, run_id="r1")

    out = DeltaTable(str(path)).to_pandas()
    assert len(out) == 2
    assert set(out.columns) >= {"id_reel", "ownerUsername", "cluster_label", "content_type"}
    assert out.loc[out["id_reel"] == "r2", "cluster_label"].iloc[0] == -1
    assert (out["content_type"] == "reel").all()


def test_write_clusters_falha_com_mensagem_clara_se_faltar_coluna(tmp_path):
    df_incompleto = _reels_clusterizados().drop(columns=["algo_name"])

    with pytest.raises(ValueError, match="algo_name"):
        ModelEnricher().write_clusters(df_incompleto, tmp_path / "governor_clusters", run_id="r1")


def test_write_clusters_falha_com_mensagem_clara_se_faltar_content_type(tmp_path):
    """ADR 0020 (Ficha 2 / issue #87): `content_type` é obrigatória --
    sem ela não dá pra distinguir reel de feed na mesma tabela."""
    df_incompleto = _reels_clusterizados().drop(columns=["content_type"])

    with pytest.raises(ValueError, match="content_type"):
        ModelEnricher().write_clusters(df_incompleto, tmp_path / "governor_clusters", run_id="r1")


def test_write_clusters_grava_reel_e_feed_juntos_sem_colidir(tmp_path):
    """ADR 0020 (Ficha 2 / issue #87): a clusterização de posts do feed
    grava em `governor_clusters` (tabela existente) ao lado das linhas de
    reel já existentes, discriminadas por `content_type` -- não uma tabela
    nova. Uma única escrita combinando os dois DataFrames (o padrão que
    `run_deterministic_modeling` usa) precisa preservar as linhas das duas
    granularidades."""
    path = tmp_path / "governor_clusters"
    df_combinado = pd.concat(
        [_reels_clusterizados(), _feed_clusterizados()], ignore_index=True
    )

    ModelEnricher().write_clusters(df_combinado, path, run_id="r1")

    out = DeltaTable(str(path)).to_pandas()
    assert len(out) == 4
    assert set(out["content_type"].unique()) == {"reel", "feed"}
    assert set(out.loc[out["content_type"] == "reel", "id_reel"]) == {"r1", "r2"}
    assert set(out.loc[out["content_type"] == "feed", "id_reel"]) == {"p1", "p2"}
    # Nenhuma linha perdida/sobrescrita entre as duas granularidades.
    assert out["id_reel"].nunique() == 4


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


def _growth_metrics():
    # Mesmo formato de saída de `compute_growth_metrics` (ADR 0020, Ficha 7
    # / issue #92) -- uma linha por perfil, com `nota`/`ilustrativo` sempre
    # presentes (ver `src/modeling/growth_history.py`).
    return pd.DataFrame(
        {
            "inputUrl": ["https://www.instagram.com/governador_a/"],
            "valor_inicial": [100.0],
            "valor_final": [121.0],
            "cmgr": [0.1],
            "cmgr_n_periodos": [3],
            "cmgr_confiavel": [False],
            "cmgr_motivo": [None],
            "retencao": [0.9],
            "retencao_n_periodos": [3],
            "retencao_n_pares_validos": [2],
            "retencao_confiavel": [False],
            "retencao_motivo": [None],
            "ilustrativo": [True],
            "nota": ["CMGR/retencao ilustrativos: poucas execucoes acumuladas."],
        }
    )


def test_write_growth_metrics_grava_uma_linha_por_perfil(tmp_path):
    path = tmp_path / "governor_growth_metrics"
    ModelEnricher().write_growth_metrics(_growth_metrics(), path, run_id="r1")

    out = DeltaTable(str(path)).to_pandas()
    assert len(out) == 1
    assert out.loc[0, "cmgr"] == pytest.approx(0.1)
    assert out.loc[0, "ilustrativo"] == True  # noqa: E712 (valor vindo do Delta, comparar como bool simples)


def test_write_growth_metrics_falha_com_mensagem_clara_se_faltar_coluna(tmp_path):
    df_incompleto = _growth_metrics().drop(columns=["ilustrativo"])

    with pytest.raises(ValueError, match="ilustrativo"):
        ModelEnricher().write_growth_metrics(
            df_incompleto, tmp_path / "governor_growth_metrics", run_id="r1"
        )


def test_write_growth_metrics_e_overwrite_por_padrao(tmp_path):
    # Snapshot recalculável, não histórico incremental -- ver docstring de
    # `write_growth_metrics`. Uma segunda escrita substitui a primeira em
    # vez de acumular.
    path = tmp_path / "governor_growth_metrics"
    ModelEnricher().write_growth_metrics(_growth_metrics(), path, run_id="r1")
    ModelEnricher().write_growth_metrics(_growth_metrics(), path, run_id="r2")

    out = DeltaTable(str(path)).to_pandas()
    assert len(out) == 1
    assert out.loc[0, "_run_id"] == "r2"
