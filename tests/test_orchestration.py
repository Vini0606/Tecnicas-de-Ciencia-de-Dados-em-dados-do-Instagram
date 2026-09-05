import json
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
from deltalake import DeltaTable

from src.features.gold.model_enricher import ModelEnricher
from src.modeling.config import ClusterConfig, GeminiRefinerConfig, ModelingConfig, PostPerformanceConfig
from src.modeling.orchestration import run_deterministic_modeling, refine_topics_with_gemini
from src.modeling.post_performance import PostPerformanceStageResult


def _df_reels():
    rng = np.random.default_rng(0)
    grupo_a = rng.normal(loc=(50, 500, 5000, 30), scale=1.0, size=(6, 4))
    grupo_b = rng.normal(loc=(5, 50, 500, 90), scale=1.0, size=(6, 4))
    dados = np.vstack([grupo_a, grupo_b])
    df = pd.DataFrame(
        dados, columns=["commentsCount", "likesCount", "videoPlayCount", "videoDuration"]
    )
    df["id"] = [f"reel_{i}" for i in range(len(df))]
    df["ownerUsername"] = "governador_teste"
    return df


def _df_comments():
    return pd.DataFrame(
        {
            "id_comment": ["c1", "c2", "c3"],
            "text": ["ótimo trabalho", "péssimo governo", "concordo com a proposta"],
        }
    )


def _df_posts_placeholder():
    """Usada só nos testes que fazem monkeypatch de `classify_post_topics`
    e `run_post_performance_stage` -- conteúdo irrelevante, os fakes não
    olham para as colunas."""
    return pd.DataFrame({"id": ["p1"], "caption": ["texto qualquer"]})


def _df_engagement_placeholder():
    return pd.DataFrame(
        {
            "id": ["governador_teste"],
            "_WC_COMENTARIO": [1.0],
            "FREQUENCIA": [1.0],
            "followersCount": [1000],
        }
    )


def _fake_analyze_sentiment(df_comments, config):
    df = df_comments.copy()
    df["sentiment_label"] = "Positive"
    df["sentiment_score"] = 0.9
    return df


def _make_fake_model_topics(nome_provisorio, nome_refinado):
    def _fake_model_topics(docs, config, embedding_model=None):
        topic_model = MagicMock()
        topic_model.get_document_info.return_value = pd.DataFrame(
            {"Document": docs, "Topic": [0] * len(docs), "Name": [nome_refinado] * len(docs)}
        )
        document_info_provisorio = pd.DataFrame(
            {"Document": docs, "Topic": [0] * len(docs), "Name": [nome_provisorio] * len(docs)}
        )
        return topic_model, [0] * len(docs), np.zeros(len(docs)), document_info_provisorio

    return _fake_model_topics


def _fake_classify_post_topics(df_posts, config, preprocessing_config=None, embedding_model=None):
    """Fake leve (issue #74 já testa `classify_post_topics` de verdade em
    `tests/test_topics.py`) -- aqui só precisa devolver `df_posts` com uma
    coluna `Topic` para não travar `run_post_performance_stage`."""
    topic_model = MagicMock()
    df_final = df_posts.copy()
    df_final["Topic"] = 0
    return topic_model, df_final


_EMPTY_COEFFICIENTS_COLUMNS = [
    "grupo",
    "preditor",
    "coeficiente",
    "r2_treino",
    "r2_holdout",
    "n_treino",
    "n_holdout",
    "alpha",
]
_EMPTY_PREDICTIONS_COLUMNS = ["id", "inputUrl", "grupo", "y_real", "y_previsto", "residuo"]


def _fake_run_post_performance_stage(df_posts, df_reels, df_engagement, config):
    """Fake usado nos testes que não são sobre performance-por-post em si --
    devolve tabelas vazias, mas com o schema certo, para que a escrita Gold
    da nova etapa não quebre nem precise de dado real."""
    return PostPerformanceStageResult(
        coefficients=pd.DataFrame(columns=_EMPTY_COEFFICIENTS_COLUMNS),
        predictions=pd.DataFrame(columns=_EMPTY_PREDICTIONS_COLUMNS),
    )


def _fake_apply_gemini_refinement(topic_model, docs, config):
    return topic_model


def _patch_post_performance_fakes(monkeypatch):
    monkeypatch.setattr(
        "src.modeling.orchestration.classify_post_topics", _fake_classify_post_topics
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.run_post_performance_stage",
        _fake_run_post_performance_stage,
    )


def test_run_deterministic_modeling_grava_clusters_e_sentimento_com_mesmo_run_id(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "src.modeling.orchestration.analyze_sentiment", _fake_analyze_sentiment
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.model_topics",
        _make_fake_model_topics("0_provisorio", "0_refinado"),
    )
    _patch_post_performance_fakes(monkeypatch)

    config = ModelingConfig(
        cluster=ClusterConfig(max_evals_per_algo=10, random_state=42, max_n_clusters=5),
        gold_clusters_path=tmp_path / "governor_clusters",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )

    result = run_deterministic_modeling(
        _df_reels(), _df_comments(), _df_posts_placeholder(), _df_engagement_placeholder(), config
    )

    clusters_out = DeltaTable(str(config.gold_clusters_path)).to_pandas()
    sentiment_out = DeltaTable(str(config.gold_sentiment_path)).to_pandas()

    assert len(clusters_out) == len(_df_reels())
    assert (clusters_out["_run_id"] == result.run_id).all()
    assert (sentiment_out["_run_id"] == result.run_id).all()
    assert (sentiment_out["Name"] == "0_provisorio").all()

    checkpoint_dir = config.checkpoints_dir / result.run_id
    assert (checkpoint_dir / "metadata.json").exists()
    assert (checkpoint_dir / "df_reels.parquet").exists()
    assert (checkpoint_dir / "df_comments.parquet").exists()
    assert (checkpoint_dir / "pca_model.joblib").exists()
    assert (checkpoint_dir / "cluster_model.joblib").exists()


def test_run_deterministic_modeling_grava_sentimento_tambem_no_historico_em_append(
    monkeypatch, tmp_path
):
    """Issue #52: além de `governor_sentiment` (overwrite, como sempre), a
    modelagem determinística agora também grava `governor_sentiment_history`
    em modo append -- sem isso não há como acumular tendência de sentimento
    ao longo do tempo (mesmo raciocínio do PR #49 para engajamento)."""
    monkeypatch.setattr(
        "src.modeling.orchestration.analyze_sentiment", _fake_analyze_sentiment
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.model_topics",
        _make_fake_model_topics("0_provisorio", "0_refinado"),
    )
    _patch_post_performance_fakes(monkeypatch)

    config = ModelingConfig(
        cluster=ClusterConfig(max_evals_per_algo=10, random_state=42, max_n_clusters=5),
        gold_clusters_path=tmp_path / "governor_clusters",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )

    result = run_deterministic_modeling(
        _df_reels(), _df_comments(), _df_posts_placeholder(), _df_engagement_placeholder(), config
    )

    sentiment_out = DeltaTable(str(config.gold_sentiment_path)).to_pandas()
    history_out = DeltaTable(str(config.gold_sentiment_history_path)).to_pandas()

    assert (sentiment_out["_run_id"] == result.run_id).all()
    assert (history_out["_run_id"] == result.run_id).all()
    assert len(history_out) == len(sentiment_out)
    # Mesma execução -- as duas tabelas precisam do mesmo _generated_at, não
    # dois `datetime.now()` levemente diferentes (ver test_model_enricher.py).
    assert (sentiment_out["_generated_at"] == history_out["_generated_at"].iloc[0]).all()


def test_refine_topics_with_gemini_nao_grava_no_historico_de_sentimento(monkeypatch, tmp_path):
    """Issue #52: o refinamento via Gemini reescreve só `Topic`/`Name` sob um
    `run_id` novo, sem gerar uma nova medição de sentimento -- gravar no
    histórico duplicaria pontos próximos no tempo com o mesmo
    sentiment_label/score, distorcendo qualquer gráfico de tendência."""
    monkeypatch.setattr(
        "src.modeling.orchestration.analyze_sentiment", _fake_analyze_sentiment
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.model_topics",
        _make_fake_model_topics("0_provisorio", "0_refinado"),
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.apply_gemini_refinement", _fake_apply_gemini_refinement
    )
    _patch_post_performance_fakes(monkeypatch)

    config = ModelingConfig(
        cluster=ClusterConfig(max_evals_per_algo=10, random_state=42, max_n_clusters=5),
        gold_clusters_path=tmp_path / "governor_clusters",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )
    result = run_deterministic_modeling(
        _df_reels(), _df_comments(), _df_posts_placeholder(), _df_engagement_placeholder(), config
    )

    calls = []
    original_write_sentiment = ModelEnricher.write_sentiment

    def spy_write_sentiment(self, df, path, run_id, mode="overwrite"):
        calls.append((str(path), mode))
        return original_write_sentiment(self, df, path, run_id, mode=mode)

    monkeypatch.setattr(ModelEnricher, "write_sentiment", spy_write_sentiment)

    gemini_config = GeminiRefinerConfig(
        api_key="fake-key", gold_sentiment_path=tmp_path / "governor_sentiment"
    )
    refine_topics_with_gemini(result.topic_model, result.docs, result.df_comments, gemini_config)

    assert calls == [(str(gemini_config.gold_sentiment_path), "overwrite")]

    # Histórico continua só com a linha da modelagem determinística original
    # -- o refinamento não acrescentou nada a ele.
    history_out = DeltaTable(str(config.gold_sentiment_history_path)).to_pandas()
    assert (history_out["_run_id"] == result.run_id).all()


def test_run_deterministic_modeling_grava_parent_run_id_como_primeira_linha_do_log(
    monkeypatch, tmp_path
):
    """Rastreabilidade completa (dados -> modelo, pedido do usuario) exige
    que quem abrir so o arquivo de log da modelagem, sem checar o
    checkpoint, ja saiba de qual execucao ela veio."""
    monkeypatch.setattr(
        "src.modeling.orchestration.analyze_sentiment", _fake_analyze_sentiment
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.model_topics",
        _make_fake_model_topics("0_provisorio", "0_refinado"),
    )
    _patch_post_performance_fakes(monkeypatch)

    config = ModelingConfig(
        cluster=ClusterConfig(max_evals_per_algo=10, random_state=42, max_n_clusters=5),
        gold_clusters_path=tmp_path / "governor_clusters",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )

    result = run_deterministic_modeling(
        _df_reels(),
        _df_comments(),
        _df_posts_placeholder(),
        _df_engagement_placeholder(),
        config,
        parent_run_id="run_extracao_pai",
    )

    assert result.parent_run_id == "run_extracao_pai"

    log_path = config.logs_dir / result.run_id / "pipeline.log"
    primeira_linha = log_path.read_text(encoding="utf-8").splitlines()[0]
    assert "parent_run_id: run_extracao_pai" in primeira_linha

    metadata = json.loads(
        (config.checkpoints_dir / result.run_id / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["parent_run_id"] == "run_extracao_pai"


def test_refine_topics_with_gemini_so_reescreve_sentimento_com_run_id_novo(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "src.modeling.orchestration.analyze_sentiment", _fake_analyze_sentiment
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.model_topics",
        _make_fake_model_topics("0_provisorio", "0_refinado"),
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.apply_gemini_refinement", _fake_apply_gemini_refinement
    )
    _patch_post_performance_fakes(monkeypatch)

    config = ModelingConfig(
        cluster=ClusterConfig(max_evals_per_algo=10, random_state=42, max_n_clusters=5),
        gold_clusters_path=tmp_path / "governor_clusters",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )
    result = run_deterministic_modeling(
        _df_reels(), _df_comments(), _df_posts_placeholder(), _df_engagement_placeholder(), config
    )

    gemini_config = GeminiRefinerConfig(
        api_key="fake-key", gold_sentiment_path=tmp_path / "governor_sentiment"
    )
    refinement = refine_topics_with_gemini(
        result.topic_model, result.docs, result.df_comments, gemini_config
    )

    assert refinement.run_id != result.run_id

    sentiment_out = DeltaTable(str(gemini_config.gold_sentiment_path)).to_pandas()
    clusters_out = DeltaTable(str(config.gold_clusters_path)).to_pandas()

    # A segunda escrita é overwrite: só o run_id do refinamento sobra em
    # governor_sentiment, com os rótulos finais.
    assert (sentiment_out["_run_id"] == refinement.run_id).all()
    assert (sentiment_out["Name"] == "0_refinado").all()

    # governor_clusters não é tocado pelo refinamento de tópicos.
    assert (clusters_out["_run_id"] == result.run_id).all()


# ---------------------------------------------------------------------------
# ADR 0019 (parte C): estágio novo [PERFORMANCE-POR-POST].
# ---------------------------------------------------------------------------

N_GOVERNADORES_PERFORMANCE = 6
POSTS_POR_GOVERNADOR_PERFORMANCE = 4


def _df_engagement_performance():
    rng = np.random.default_rng(10)
    ids = [f"gov{i}" for i in range(N_GOVERNADORES_PERFORMANCE)]
    return pd.DataFrame(
        {
            "id": ids,
            "_WC_COMENTARIO": 1.5,
            "FREQUENCIA": rng.uniform(0.1, 2.0, size=N_GOVERNADORES_PERFORMANCE),
            "followersCount": rng.integers(10_000, 500_000, size=N_GOVERNADORES_PERFORMANCE),
        }
    )


def _df_reels_performance(df_engagement):
    rng = np.random.default_rng(11)
    linhas = []
    for gov in df_engagement["id"]:
        for j in range(POSTS_POR_GOVERNADOR_PERFORMANCE):
            linhas.append(
                {
                    "id": f"{gov}_reel_{j}",
                    "ownerId": gov,
                    "ownerUsername": gov,
                    "inputUrl": f"https://instagram.com/{gov}",
                    "commentsCount": int(rng.integers(0, 200)),
                    "likesCount": int(rng.integers(0, 5000)),
                    "data_hora": pd.Timestamp("2026-01-01")
                    + pd.Timedelta(days=j, hours=int(rng.integers(0, 24))),
                    "type_raw": "Video",
                    "videoDuration": float(rng.uniform(5, 90)),
                    "videoPlayCount": int(rng.integers(100, 100_000)),
                    "isSponsored": bool(rng.integers(0, 2)),
                }
            )
    return pd.DataFrame(linhas)


def _df_posts_performance(df_engagement):
    rng = np.random.default_rng(12)
    linhas = []
    for gov in df_engagement["id"]:
        for j in range(POSTS_POR_GOVERNADOR_PERFORMANCE):
            linhas.append(
                {
                    "id": f"{gov}_post_{j}",
                    "ownerId": gov,
                    "ownerUsername": gov,
                    "inputUrl": f"https://instagram.com/{gov}",
                    "commentsCount": int(rng.integers(0, 200)),
                    "likesCount": int(rng.integers(0, 5000)),
                    "data_hora": pd.Timestamp("2026-01-01")
                    + pd.Timedelta(days=j, hours=int(rng.integers(0, 24))),
                    "type_raw": rng.choice(["Image", "Sidecar"]),
                    "videoDuration": np.nan,
                    "caption": f"legenda {j} do governador {gov}",
                    "hashtags": None,
                }
            )
    return pd.DataFrame(linhas)


def _config_performance(tmp_path):
    return ModelingConfig(
        cluster=ClusterConfig(max_evals_per_algo=10, random_state=42, max_n_clusters=5),
        post_performance=PostPerformanceConfig(holdout_governors_count=2, lasso_cv_folds=2),
        gold_clusters_path=tmp_path / "governor_clusters",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )


def test_run_deterministic_modeling_grava_coeficientes_e_previsoes_de_performance_por_post(
    monkeypatch, tmp_path
):
    """ADR 0019 (parte C): o novo passo roda de verdade (Lasso real sobre
    dado sintético pequeno) e persiste as duas tabelas Gold novas sob o
    mesmo `run_id` da execução -- só `classify_post_topics` é fake (já
    coberto em tests/test_topics.py), o resto do estágio é real."""
    monkeypatch.setattr(
        "src.modeling.orchestration.analyze_sentiment", _fake_analyze_sentiment
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.model_topics",
        _make_fake_model_topics("0_provisorio", "0_refinado"),
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.classify_post_topics", _fake_classify_post_topics
    )

    df_engagement = _df_engagement_performance()
    df_reels = _df_reels_performance(df_engagement)
    df_posts = _df_posts_performance(df_engagement)
    config = _config_performance(tmp_path)

    result = run_deterministic_modeling(df_reels, _df_comments(), df_posts, df_engagement, config)

    coefficients_out = DeltaTable(
        str(config.gold_post_performance_coefficients_path)
    ).to_pandas()
    predictions_out = DeltaTable(str(config.gold_post_performance_predictions_path)).to_pandas()

    assert (coefficients_out["_run_id"] == result.run_id).all()
    assert (predictions_out["_run_id"] == result.run_id).all()
    assert set(coefficients_out["grupo"].unique()) == {"video", "estatico"}
    assert set(predictions_out["grupo"].unique()) == {"video", "estatico"}
    assert len(predictions_out) == len(df_reels) + len(df_posts)


def test_run_deterministic_modeling_degrada_sem_derrubar_pipeline_se_performance_por_post_falhar(
    monkeypatch, tmp_path
):
    """User story 13 (issue #75): dado insuficiente (ou qualquer outra
    falha) na etapa de performance-por-post não pode derrubar PCA/
    clustering/sentimento/tópicos, que já rodaram com sucesso na mesma
    execução -- a etapa só é pulada."""
    monkeypatch.setattr(
        "src.modeling.orchestration.analyze_sentiment", _fake_analyze_sentiment
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.model_topics",
        _make_fake_model_topics("0_provisorio", "0_refinado"),
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.classify_post_topics", _fake_classify_post_topics
    )

    def _fake_run_post_performance_stage_falha(df_posts, df_reels, df_engagement, config):
        raise ValueError("dado insuficiente para treinar")

    monkeypatch.setattr(
        "src.modeling.orchestration.run_post_performance_stage",
        _fake_run_post_performance_stage_falha,
    )

    config = ModelingConfig(
        cluster=ClusterConfig(max_evals_per_algo=10, random_state=42, max_n_clusters=5),
        gold_clusters_path=tmp_path / "governor_clusters",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )

    result = run_deterministic_modeling(
        _df_reels(), _df_comments(), _df_posts_placeholder(), _df_engagement_placeholder(), config
    )

    # Os demais estágios completaram normalmente, apesar da falha.
    clusters_out = DeltaTable(str(config.gold_clusters_path)).to_pandas()
    assert (clusters_out["_run_id"] == result.run_id).all()
    checkpoint_dir = config.checkpoints_dir / result.run_id
    assert (checkpoint_dir / "metadata.json").exists()

    # A etapa pulada não deixou as tabelas novas para trás.
    assert not config.gold_post_performance_coefficients_path.exists()
    assert not config.gold_post_performance_predictions_path.exists()
