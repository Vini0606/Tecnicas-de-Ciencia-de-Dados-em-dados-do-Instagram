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
    # `inputUrl` presente (mesma convenção de `SILVER_COMMENTS_SCHEMA`) para
    # exercitar o NSM (ADR 0020 Ficha 5 / issue #90), que junta
    # `governor_sentiment` a `governor_engagement` por essa coluna -- mesmo
    # perfil de `_df_engagement_placeholder()` abaixo.
    return pd.DataFrame(
        {
            "id_comment": ["c1", "c2", "c3"],
            "text": ["ótimo trabalho", "péssimo governo", "concordo com a proposta"],
            "inputUrl": "https://instagram.com/governador_teste",
        }
    )


def _df_posts_placeholder():
    """Usada nos testes que fazem monkeypatch de `classify_post_topics` e
    `run_post_performance_stage` -- o conteúdo de `caption`/`Topic` é
    irrelevante (os fakes não olham pra essas colunas), mas
    `commentsCount`/`likesCount`/`ownerUsername` precisam existir e ter
    linhas suficientes porque a clusterização de posts do feed (ADR 0020,
    Ficha 2 / issue #87) roda de verdade nesses testes, sem mock."""
    rng = np.random.default_rng(1)
    grupo_a = rng.normal(loc=(5, 50), scale=1.0, size=(6, 2))
    grupo_b = rng.normal(loc=(50, 5), scale=1.0, size=(6, 2))
    dados = np.vstack([grupo_a, grupo_b])
    df = pd.DataFrame(dados, columns=["commentsCount", "likesCount"])
    df["id"] = [f"post_{i}" for i in range(len(df))]
    df["ownerUsername"] = "governador_teste"
    df["caption"] = "texto qualquer"
    return df


def _df_engagement_placeholder():
    # `inputUrl`/`username`/`TOTAL ENGAJAMENTO`/`count` presentes (mesmas
    # colunas de `GOLD_ENGAGEMENT_SCHEMA`) para exercitar o NSM (ADR 0020
    # Ficha 5 / issue #90) -- mesmo `inputUrl` de `_df_comments()` acima.
    return pd.DataFrame(
        {
            "id": ["governador_teste"],
            "username": ["governador_teste"],
            "inputUrl": ["https://instagram.com/governador_teste"],
            "_WC_COMENTARIO": [1.0],
            "FREQUENCIA": [1.0],
            "followersCount": [1000],
            "TOTAL ENGAJAMENTO": [100],
            "count": [10],
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
        gold_clusters_reels_path=tmp_path / "governor_clusters_reels",
        gold_clusters_posts_path=tmp_path / "governor_clusters_posts",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
        gold_nsm_path=tmp_path / "governor_nsm",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        gold_profile_clusters_engagement_path=tmp_path / "governor_profile_clusters_engagement",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )

    result = run_deterministic_modeling(
        _df_reels(), _df_comments(), _df_posts_placeholder(), _df_engagement_placeholder(), config
    )

    clusters_reels_out = DeltaTable(str(config.gold_clusters_reels_path)).to_pandas()
    clusters_posts_out = DeltaTable(str(config.gold_clusters_posts_path)).to_pandas()
    sentiment_out = DeltaTable(str(config.gold_sentiment_path)).to_pandas()

    # issue #152: `governor_clusters` deixou de ser uma tabela única
    # combinando reels e posts do feed via `pd.concat` (que duplicava
    # posts sobrepostos entre `posts_clean`/`reels_clean`) e virou duas
    # tabelas Gold separadas, uma por formato.
    assert len(clusters_reels_out) == len(_df_reels())
    assert len(clusters_posts_out) == len(_df_posts_placeholder())
    assert (clusters_reels_out["content_type"] == "reel").all()
    assert (clusters_posts_out["content_type"] == "feed").all()
    assert (clusters_reels_out["_run_id"] == result.run_id).all()
    assert (clusters_posts_out["_run_id"] == result.run_id).all()
    assert (sentiment_out["_run_id"] == result.run_id).all()
    # ADR 0020 (Ficha 3) / issue #88: `governor_sentiment` agora também
    # recebe legenda/transcrição (fonte "legenda"/"transcricao") -- só a
    # fonte "comentario" passa por BERTopic nesta issue, então `Name` só é
    # populado para ela (ver teste dedicado abaixo para as outras fontes).
    comentarios_out = sentiment_out[sentiment_out["fonte"] == "comentario"]
    assert (comentarios_out["Name"] == "0_provisorio").all()

    checkpoint_dir = config.checkpoints_dir / result.run_id
    assert (checkpoint_dir / "metadata.json").exists()
    assert (checkpoint_dir / "df_reels.parquet").exists()
    assert (checkpoint_dir / "df_comments.parquet").exists()
    assert (checkpoint_dir / "pca_model.joblib").exists()
    assert (checkpoint_dir / "cluster_model.joblib").exists()


def test_run_deterministic_modeling_grava_score_ice_por_topico_de_comentario(
    monkeypatch, tmp_path
):
    """ADR 0020 (Ficha 6) / issue #91: `topic_priority_score` recebe uma
    linha por tópico de COMENTÁRIO (não de discurso oficial) -- calculada a
    partir do `df_comments_final` já com sentimento/tópico, no mesmo
    `run_id` das demais tabelas desta execução."""
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
        gold_clusters_reels_path=tmp_path / "governor_clusters_reels",
        gold_clusters_posts_path=tmp_path / "governor_clusters_posts",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
        gold_nsm_path=tmp_path / "governor_nsm",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        gold_profile_clusters_engagement_path=tmp_path / "governor_profile_clusters_engagement",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )

    result = run_deterministic_modeling(
        _df_reels(), _df_comments(), _df_posts_placeholder(), _df_engagement_placeholder(), config
    )

    priority_out = DeltaTable(str(config.gold_topic_priority_score_path)).to_pandas()

    # `_fake_model_topics` coloca todos os 3 comentários no mesmo Topic 0 --
    # uma linha só no resultado, com o Name provisório (mesmo tópico
    # "cru" gravado em governor_sentiment, ver teste acima).
    assert len(priority_out) == 1
    assert priority_out.loc[0, "Topic"] == 0
    assert priority_out.loc[0, "Name"] == "0_provisorio"
    assert priority_out.loc[0, "n_comentarios"] == 3
    assert (priority_out["_run_id"] == result.run_id).all()
    for componente in ("impacto", "confianca", "facilidade", "score"):
        assert 0.0 <= priority_out.loc[0, componente] <= 1.0


def test_run_deterministic_modeling_grava_nsm_por_perfil(monkeypatch, tmp_path):
    """ADR 0020 (Ficha 5) / issue #90: `governor_nsm` recebe uma linha por
    perfil (`inputUrl`), calculada a partir do `df_comments_final` já com
    sentimento (mesmo `governor_sentiment` gravado nesta execução, fonte
    "comentario") e do `df_engagement` recebido por esta função -- mesma
    posição/dependência do Score ICE (teste acima), no mesmo `run_id`."""
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
        gold_clusters_reels_path=tmp_path / "governor_clusters_reels",
        gold_clusters_posts_path=tmp_path / "governor_clusters_posts",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
        gold_nsm_path=tmp_path / "governor_nsm",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        gold_profile_clusters_engagement_path=tmp_path / "governor_profile_clusters_engagement",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )

    result = run_deterministic_modeling(
        _df_reels(), _df_comments(), _df_posts_placeholder(), _df_engagement_placeholder(), config
    )

    nsm_out = DeltaTable(str(config.gold_nsm_path)).to_pandas()

    # `_fake_analyze_sentiment` marca os 3 comentários como "Positive" --
    # proporcao_positivos = 1.0; `_df_engagement_placeholder` tem
    # TOTAL ENGAJAMENTO=100/count=10 -> alcance_medio=10.0 -> nsm=10.0.
    assert len(nsm_out) == 1
    linha = nsm_out.iloc[0]
    assert linha["inputUrl"] == "https://instagram.com/governador_teste"
    assert linha["n_comentarios_totais"] == 3
    assert linha["proporcao_positivos"] == 1.0
    assert linha["alcance_medio"] == 10.0
    assert linha["nsm"] == 10.0
    assert (nsm_out["_run_id"] == result.run_id).all()


def _df_reels_com_transcript():
    """Mesma base de `_df_reels()`, mas com `transcript` -- uma linha com
    fala real, outra nula (nem todo reel tem transcrição) -- e `data_hora`,
    para exercitar `_build_text_sentiment_source` de verdade (ADR 0020
    Ficha 3 / issue #88)."""
    df = _df_reels()
    df["transcript"] = [None] * (len(df) - 1) + [
        "estamos trabalhando para melhorar a saude da populacao"
    ]
    df["data_hora"] = pd.Timestamp("2026-05-01")
    return df


def test_run_deterministic_modeling_grava_sentimento_de_legenda_e_transcricao(
    monkeypatch, tmp_path
):
    """ADR 0020 (Ficha 3) / issue #88: `governor_sentiment` passa a receber,
    além dos comentários, uma linha por legenda de post (`caption`) e por
    transcrição de reel (`transcript`), distinguidas pela coluna `fonte` --
    sem que nenhuma fonte apague a outra (todas as escritas depois da
    primeira usam `mode="append"`)."""
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
        gold_clusters_reels_path=tmp_path / "governor_clusters_reels",
        gold_clusters_posts_path=tmp_path / "governor_clusters_posts",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
        gold_nsm_path=tmp_path / "governor_nsm",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        gold_profile_clusters_engagement_path=tmp_path / "governor_profile_clusters_engagement",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )

    df_posts = _df_posts_placeholder()  # id="post_0".."post_11", caption="texto qualquer"
    df_reels = _df_reels_com_transcript()

    run_deterministic_modeling(
        df_reels, _df_comments(), df_posts, _df_engagement_placeholder(), config
    )

    sentiment_out = DeltaTable(str(config.gold_sentiment_path)).to_pandas()

    assert set(sentiment_out["fonte"]) == {"comentario", "legenda", "transcricao"}

    legenda_out = sentiment_out[sentiment_out["fonte"] == "legenda"]
    assert len(legenda_out) == len(df_posts)
    assert legenda_out.iloc[0]["id_reel"] == "post_0"
    assert legenda_out.iloc[0]["text"] == "texto qualquer"

    transcricao_out = sentiment_out[sentiment_out["fonte"] == "transcricao"]
    assert len(transcricao_out) == len(df_reels)
    # A linha com transcrição real carrega o texto original -- as demais
    # (sem fala) não quebram o pipeline, só ficam com `text` nulo.
    linha_com_fala = transcricao_out[transcricao_out["text"].notna()]
    assert len(linha_com_fala) == 1
    assert (
        linha_com_fala.iloc[0]["text"]
        == "estamos trabalhando para melhorar a saude da populacao"
    )


def test_run_deterministic_modeling_grava_topicos_de_discurso_separados_de_comentario(
    monkeypatch, tmp_path
):
    """ADR 0020 (Ficha 4) / issue #89: `governor_discourse_topics` recebe os
    tópicos do corpus de discurso oficial (legenda+transcrição combinadas
    num único corpus/modelo) -- tabela própria, não misturada a
    `governor_sentiment` (que continua sem Topic/Name para essas duas
    fontes, exatamente como antes desta issue)."""
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
        gold_clusters_reels_path=tmp_path / "governor_clusters_reels",
        gold_clusters_posts_path=tmp_path / "governor_clusters_posts",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
        gold_nsm_path=tmp_path / "governor_nsm",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        gold_profile_clusters_engagement_path=tmp_path / "governor_profile_clusters_engagement",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )

    df_posts = _df_posts_placeholder()  # 12 posts, caption="texto qualquer"
    df_reels = _df_reels_com_transcript()  # 12 reels, 1 com transcript real

    run_deterministic_modeling(
        df_reels, _df_comments(), df_posts, _df_engagement_placeholder(), config
    )

    discourse_out = DeltaTable(str(config.gold_discourse_topics_path)).to_pandas()

    # Uma linha por documento de cada fonte -- legenda (posts) + transcrição
    # (reels), nunca por comentário.
    assert len(discourse_out) == len(df_posts) + len(df_reels)
    assert set(discourse_out["fonte"]) == {"legenda", "transcricao"}
    # Tópicos vieram do `model_topics` fake (mesmo usado para comentários,
    # mas chamado de novo sobre o corpus de discurso) -- rótulo provisório,
    # não o refinado via Gemini (que não toca esta tabela).
    assert (discourse_out["Name"] == "0_provisorio").all()

    # Não mistura com governor_sentiment: as linhas de legenda/transcrição
    # lá continuam sem Topic/Name (comportamento inalterado da issue #88 --
    # só a fonte "comentario" passa por tópicos nessa tabela).
    sentiment_out = DeltaTable(str(config.gold_sentiment_path)).to_pandas()
    legenda_sentiment = sentiment_out[sentiment_out["fonte"] == "legenda"]
    assert legenda_sentiment["Topic"].isna().all()


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
        gold_clusters_reels_path=tmp_path / "governor_clusters_reels",
        gold_clusters_posts_path=tmp_path / "governor_clusters_posts",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
        gold_nsm_path=tmp_path / "governor_nsm",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        gold_profile_clusters_engagement_path=tmp_path / "governor_profile_clusters_engagement",
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
        gold_clusters_reels_path=tmp_path / "governor_clusters_reels",
        gold_clusters_posts_path=tmp_path / "governor_clusters_posts",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
        gold_nsm_path=tmp_path / "governor_nsm",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        gold_profile_clusters_engagement_path=tmp_path / "governor_profile_clusters_engagement",
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
        api_key="fake-key",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
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
        gold_clusters_reels_path=tmp_path / "governor_clusters_reels",
        gold_clusters_posts_path=tmp_path / "governor_clusters_posts",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
        gold_nsm_path=tmp_path / "governor_nsm",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        gold_profile_clusters_engagement_path=tmp_path / "governor_profile_clusters_engagement",
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
        gold_clusters_reels_path=tmp_path / "governor_clusters_reels",
        gold_clusters_posts_path=tmp_path / "governor_clusters_posts",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
        gold_nsm_path=tmp_path / "governor_nsm",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        gold_profile_clusters_engagement_path=tmp_path / "governor_profile_clusters_engagement",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )
    result = run_deterministic_modeling(
        _df_reels(), _df_comments(), _df_posts_placeholder(), _df_engagement_placeholder(), config
    )

    gemini_config = GeminiRefinerConfig(
        api_key="fake-key",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
    )
    refinement = refine_topics_with_gemini(
        result.topic_model, result.docs, result.df_comments, gemini_config
    )

    assert refinement.run_id != result.run_id

    sentiment_out = DeltaTable(str(gemini_config.gold_sentiment_path)).to_pandas()
    clusters_reels_out = DeltaTable(str(config.gold_clusters_reels_path)).to_pandas()

    # A segunda escrita é overwrite: só o run_id do refinamento sobra em
    # governor_sentiment, com os rótulos finais.
    assert (sentiment_out["_run_id"] == refinement.run_id).all()
    assert (sentiment_out["Name"] == "0_refinado").all()

    # governor_clusters_reels/governor_clusters_posts não são tocadas pelo
    # refinamento de tópicos.
    assert (clusters_reels_out["_run_id"] == result.run_id).all()


def test_refine_topics_with_gemini_recalcula_score_ice_com_topico_refinado(
    monkeypatch, tmp_path
):
    """ADR 0020 (Ficha 6) / issue #91: Score ICE depende de
    `governor_sentiment` já refinado via Gemini, não do rótulo provisório do
    estágio determinístico -- `topic_priority_score` precisa ser
    sobrescrito com o `Name` refinado, sob o mesmo `run_id` novo do
    refinamento."""
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
        gold_clusters_reels_path=tmp_path / "governor_clusters_reels",
        gold_clusters_posts_path=tmp_path / "governor_clusters_posts",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
        gold_nsm_path=tmp_path / "governor_nsm",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        gold_profile_clusters_engagement_path=tmp_path / "governor_profile_clusters_engagement",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )
    result = run_deterministic_modeling(
        _df_reels(), _df_comments(), _df_posts_placeholder(), _df_engagement_placeholder(), config
    )

    # Antes do refinamento: ranking provisório, com o Name "cru" do BERTopic.
    priority_out_provisorio = DeltaTable(str(config.gold_topic_priority_score_path)).to_pandas()
    assert (priority_out_provisorio["Name"] == "0_provisorio").all()
    assert (priority_out_provisorio["_run_id"] == result.run_id).all()

    gemini_config = GeminiRefinerConfig(
        api_key="fake-key",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
    )
    refinement = refine_topics_with_gemini(
        result.topic_model, result.docs, result.df_comments, gemini_config
    )

    priority_out_refinado = DeltaTable(str(gemini_config.gold_topic_priority_score_path)).to_pandas()

    # Depois do refinamento: overwrite -- só o run_id/Name do refinamento
    # sobram, o ranking provisório não persiste ao lado do refinado.
    assert len(priority_out_refinado) == 1
    assert (priority_out_refinado["_run_id"] == refinement.run_id).all()
    assert (priority_out_refinado["Name"] == "0_refinado").all()


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
            "username": ids,
            # Mesmo `inputUrl` usado por `_df_reels_performance`/
            # `_df_posts_performance` abaixo -- exercita o NSM (ADR 0020
            # Ficha 5 / issue #90) sobre este fixture também.
            "inputUrl": [f"https://instagram.com/{gov}" for gov in ids],
            "_WC_COMENTARIO": 1.5,
            "FREQUENCIA": rng.uniform(0.1, 2.0, size=N_GOVERNADORES_PERFORMANCE),
            "followersCount": rng.integers(10_000, 500_000, size=N_GOVERNADORES_PERFORMANCE),
            "TOTAL ENGAJAMENTO": rng.integers(100, 10_000, size=N_GOVERNADORES_PERFORMANCE),
            "count": rng.integers(1, 50, size=N_GOVERNADORES_PERFORMANCE),
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
        gold_clusters_reels_path=tmp_path / "governor_clusters_reels",
        gold_clusters_posts_path=tmp_path / "governor_clusters_posts",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
        gold_nsm_path=tmp_path / "governor_nsm",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        gold_profile_clusters_engagement_path=tmp_path / "governor_profile_clusters_engagement",
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
        gold_clusters_reels_path=tmp_path / "governor_clusters_reels",
        gold_clusters_posts_path=tmp_path / "governor_clusters_posts",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
        gold_nsm_path=tmp_path / "governor_nsm",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        gold_profile_clusters_engagement_path=tmp_path / "governor_profile_clusters_engagement",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )

    result = run_deterministic_modeling(
        _df_reels(), _df_comments(), _df_posts_placeholder(), _df_engagement_placeholder(), config
    )

    # Os demais estágios completaram normalmente, apesar da falha.
    clusters_reels_out = DeltaTable(str(config.gold_clusters_reels_path)).to_pandas()
    assert (clusters_reels_out["_run_id"] == result.run_id).all()
    checkpoint_dir = config.checkpoints_dir / result.run_id
    assert (checkpoint_dir / "metadata.json").exists()

    # A etapa pulada não deixou as tabelas novas para trás.
    assert not config.gold_post_performance_coefficients_path.exists()
    assert not config.gold_post_performance_predictions_path.exists()


# ---------------------------------------------------------------------------
# Fase 2 (ADR 0020): clusterização de PERFIL de governador por engajamento,
# integrada ao estágio determinístico -- fecha a paridade com
# `lambdas/model/handler.py` (pipeline serverless já fazia isso sozinho).
# ---------------------------------------------------------------------------

N_GOVERNADORES_CLUSTER_PERFIL = 8


def _df_engagement_cluster_perfil():
    """Fixture dedicada ao estágio [CLUSTER-PERFIL] -- precisa das 3
    features de `ModelingConfig.profile_cluster` (% ENGAJAMENTO/RECENCIA/
    FREQUENCIA), além das colunas já exigidas por `NsmScorer` (mesmo padrão
    de `_df_engagement_performance`, mas com mais linhas: AutoClusterHPO
    precisa de mais pontos do que o teste de NSM usa)."""
    rng = np.random.default_rng(20)
    ids = [f"gov{i}" for i in range(N_GOVERNADORES_CLUSTER_PERFIL)]
    return pd.DataFrame(
        {
            "id": ids,
            "username": ids,
            "inputUrl": [f"https://instagram.com/{gov}" for gov in ids],
            "_WC_COMENTARIO": 1.5,
            "FREQUENCIA": rng.uniform(0.1, 2.0, size=N_GOVERNADORES_CLUSTER_PERFIL),
            "% ENGAJAMENTO": rng.uniform(0.5, 10.0, size=N_GOVERNADORES_CLUSTER_PERFIL),
            "RECENCIA": rng.integers(0, 30, size=N_GOVERNADORES_CLUSTER_PERFIL),
            "followersCount": rng.integers(10_000, 500_000, size=N_GOVERNADORES_CLUSTER_PERFIL),
            "TOTAL ENGAJAMENTO": rng.integers(100, 10_000, size=N_GOVERNADORES_CLUSTER_PERFIL),
            "count": rng.integers(1, 50, size=N_GOVERNADORES_CLUSTER_PERFIL),
        }
    )


def test_run_deterministic_modeling_grava_clusters_de_perfil_por_engajamento(
    monkeypatch, tmp_path
):
    """A modelagem determinística agora também clusteriza `df_engagement`
    por perfil (Fase 2, ADR 0020) e grava `governor_profile_clusters_engagement`
    sob o mesmo `run_id` das demais tabelas -- antes desta issue, só
    `scripts/run_profile_clustering_engagement.py` (manual) ou
    `lambdas/model/handler.py` (serverless) faziam isso; a Tela 4
    ("Comparar perfis", ADR 0021) do dashboard dependia desse passo manual e
    ficava vazia sem ele."""
    monkeypatch.setattr(
        "src.modeling.orchestration.analyze_sentiment", _fake_analyze_sentiment
    )
    monkeypatch.setattr(
        "src.modeling.orchestration.model_topics",
        _make_fake_model_topics("0_provisorio", "0_refinado"),
    )
    _patch_post_performance_fakes(monkeypatch)

    df_engagement = _df_engagement_cluster_perfil()
    config = ModelingConfig(
        cluster=ClusterConfig(max_evals_per_algo=10, random_state=42, max_n_clusters=5),
        profile_cluster=ClusterConfig(
            feature_columns=["% ENGAJAMENTO", "RECENCIA", "FREQUENCIA"],
            max_evals_per_algo=10,
            random_state=42,
            max_n_clusters=5,
        ),
        gold_clusters_reels_path=tmp_path / "governor_clusters_reels",
        gold_clusters_posts_path=tmp_path / "governor_clusters_posts",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
        gold_nsm_path=tmp_path / "governor_nsm",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        gold_profile_clusters_engagement_path=tmp_path / "governor_profile_clusters_engagement",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )

    result = run_deterministic_modeling(
        _df_reels(), _df_comments(), _df_posts_placeholder(), df_engagement, config
    )

    profile_clusters_out = DeltaTable(
        str(config.gold_profile_clusters_engagement_path)
    ).to_pandas()

    assert len(profile_clusters_out) == N_GOVERNADORES_CLUSTER_PERFIL
    assert set(profile_clusters_out["inputUrl"]) == set(df_engagement["inputUrl"])
    assert (profile_clusters_out["_run_id"] == result.run_id).all()
    assert profile_clusters_out["cluster_label"].notna().all()
    assert profile_clusters_out["cluster_algo"].notna().all()


def test_run_deterministic_modeling_degrada_sem_derrubar_pipeline_se_cluster_perfil_falhar(
    monkeypatch, tmp_path
):
    """Mesmo raciocínio da degradação de performance-por-post: `df_engagement`
    sem as colunas de `profile_cluster.feature_columns` (caso real de quem
    ainda não gerou essas colunas, ou dado sintético incompleto) não pode
    derrubar os estágios que já rodaram com sucesso -- a etapa só é pulada."""
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
        gold_clusters_reels_path=tmp_path / "governor_clusters_reels",
        gold_clusters_posts_path=tmp_path / "governor_clusters_posts",
        gold_sentiment_path=tmp_path / "governor_sentiment",
        gold_sentiment_history_path=tmp_path / "governor_sentiment_history",
        gold_discourse_topics_path=tmp_path / "governor_discourse_topics",
        gold_topic_priority_score_path=tmp_path / "topic_priority_score",
        gold_nsm_path=tmp_path / "governor_nsm",
        gold_post_performance_coefficients_path=tmp_path / "post_performance_coefficients",
        gold_post_performance_predictions_path=tmp_path / "post_performance_predictions",
        gold_profile_clusters_engagement_path=tmp_path / "governor_profile_clusters_engagement",
        checkpoints_dir=tmp_path / "checkpoints",
        logs_dir=tmp_path / "logs",
    )

    # `_df_engagement_placeholder()` não tem "% ENGAJAMENTO"/"RECENCIA" --
    # `cluster_governor_profiles` levanta KeyError ao indexar essas colunas.
    result = run_deterministic_modeling(
        _df_reels(), _df_comments(), _df_posts_placeholder(), _df_engagement_placeholder(), config
    )

    clusters_reels_out = DeltaTable(str(config.gold_clusters_reels_path)).to_pandas()
    assert (clusters_reels_out["_run_id"] == result.run_id).all()
    assert not config.gold_profile_clusters_engagement_path.exists()
