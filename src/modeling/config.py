"""Configuração dos estágios de modelagem"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from config import settings

# Padrão de token do CountVectorizer que preserva emojis como tokens
# próprios, em vez de descartá-los como pontuação. As faixas U+2600-U+26FF
# e U+2700-U+27BF (símbolos diversos / dingbats) são geradas via chr()
# para evitar embutir os glifos literais no código-fonte.
_EMOJI_RANGES = "".join(
    [
        "\U0001F300-\U0001F5FF",
        "\U0001F600-\U0001F64F",
        "\U0001F680-\U0001F6FF",
        f"{chr(0x2600)}-{chr(0x26FF)}",
        f"{chr(0x2700)}-{chr(0x27BF)}",
    ]
)
EMOJI_TOKEN_PATTERN = r"(?u)\b\w\w+\b|[" + _EMOJI_RANGES + "]"


@dataclass
class PCAConfig:
    feature_columns: list[str] = field(
        default_factory=lambda: [
            "commentsCount",
            "likesCount",
            "videoPlayCount",
            "videoDuration",
        ]
    )
    n_components: int = 2
    random_state: int | None = None


@dataclass
class FeedPCAConfig(PCAConfig):
    """PCA de engajamento de posts do feed (ADR 0020, Ficha 2 / issue #87).

    Posts do feed não têm `videoPlayCount`/`videoDuration` -- essas colunas
    só existem para vídeo (Reels; ver `SILVER_POSTS_SCHEMA`, onde ficam
    nulas para posts estáticos). O PCA de feed entra só com métricas de
    engajamento comuns a qualquer post, então suas cargas são diferentes das
    de `PCAConfig` (reel) -- isso é esperado, não um bug a corrigir."""

    feature_columns: list[str] = field(
        default_factory=lambda: ["commentsCount", "likesCount"]
    )


@dataclass
class ClusterConfig:
    feature_columns: list[str] = field(
        default_factory=lambda: ["PC1_Engajamento_videoPlay", "PC2_videoDuration"]
    )
    max_evals_per_algo: int = 100
    random_state: int = 42
    max_n_clusters: int | None = None


@dataclass
class SentimentConfig:
    """Reaproveitada para as três fontes de `governor_sentiment`
    (comentário/legenda/transcrição -- ADR 0020 Ficha 3 / issue #88): só a
    coluna de texto de entrada muda por chamada, o modelo é o mesmo.

    Limitação conhecida, documentada e não resolvida nesta rodada (fora de
    escopo da issue #88): `model_name` foi treinado em tweets (texto curto e
    informal). Legenda/transcrição de assessoria de governador são texto
    mais longo e formal -- um registro estruturalmente diferente do domínio
    de treino do modelo. `analyze_sentiment` não quebra com esse texto
    (trunca em 512 tokens), mas a qualidade do rótulo de sentimento em
    texto formal não foi validada com dado real; isso deve ser declarado
    como limitação metodológica explícita no Cap. 7 do TCC, não escondido."""

    text_column: str = "text"
    model_name: str = "cardiffnlp/twitter-xlm-roberta-base-sentiment"


@dataclass
class PreprocessingConfig:
    text_column: str = "text"
    stopwords_language: str = "portuguese"
    demoji_language: str = "pt"


@dataclass
class TopicModelConfig:
    embedding_model: str = "rufimelo/bert-large-portuguese-cased-sts"
    language: str = "multilingual"
    hdbscan_min_cluster_size: int = 15
    hdbscan_min_samples: int = 5
    # `int` fixa um alvo de mesclagem (ver `model_topics`/`reduce_topics`);
    # `"auto"` (ver `DiscourseTopicModelConfig`) deixa o BERTopic mesclar só
    # tópicos redundantes, sem forçar uma contagem alvo.
    nr_topics: int | str = 50
    calculate_probabilities: bool = True
    verbose: bool = True
    token_pattern: str = EMOJI_TOKEN_PATTERN


@dataclass
class PostTopicModelConfig(TopicModelConfig):
    """Config de BERTopic para captions de post (ADR 0019, parte B) --
    corpus de algumas centenas de documentos (não ~13,5 mil como
    comentários), então `nr_topics`/HDBSCAN bem menores que
    `TopicModelConfig` evitam fragmentar demais o preditor de Tema. Valores
    ainda placeholders (issue explicitamente deixa "a calibrar" contra o
    volume real de posts coletados), não derivados de dados reais."""

    hdbscan_min_cluster_size: int = 5
    hdbscan_min_samples: int = 2
    nr_topics: int = 15


@dataclass
class DiscourseTopicModelConfig(TopicModelConfig):
    """Config de BERTopic para o discurso oficial (legenda+transcrição, ADR
    0020 Ficha 4 / issue #89) -- corpus pequeno (~810 documentos na coleta
    atual), mesma ordem de grandeza do corpus de posts
    (`PostTopicModelConfig`), mas SEM `nr_topics` fixo: a issue #89 pede
    explicitamente que o número de tópicos emerja do volume real do corpus,
    sem forçar paridade nem com os ~50 tópicos do modelo de comentários
    (corpus ~15x maior) nem com o `nr_topics=15` fixo do modelo de posts.
    `nr_topics="auto"` deixa `reduce_topics` mesclar só tópicos redundantes
    entre si (ver `model_topics`), em vez de reduzir para uma contagem
    alvo -- volume baixo pode legitimamente produzir menos de 50 tópicos
    estáveis, o que é esperado, não um bug."""

    hdbscan_min_cluster_size: int = 5
    hdbscan_min_samples: int = 2
    nr_topics: int | str = "auto"


@dataclass
class PostPerformanceConfig:
    """Config do estágio de regressão de performance-por-post (ADR 0019,
    parte C) -- dois grupos (vídeo=Reels, estático=Posts), holdout de
    governadores compartilhado entre os dois grupos, Lasso com alpha
    escolhido por validação cruzada (`LassoCV`)."""

    holdout_governors_count: int = 7
    random_state: int = 42
    lasso_cv_folds: int = 5
    lasso_max_iter: int = 10_000
    circularity_correlation_threshold: float = 0.95
    # Colunas brutas que compõem Y (`(likesCount + commentsCount*Wc) /
    # followersCount`) -- nenhum preditor pode ser literalmente uma delas.
    raw_target_columns: tuple[str, ...] = ("likesCount", "commentsCount")
    numeric_predictors_comuns: list[str] = field(
        default_factory=lambda: ["hora_do_dia", "FREQUENCIA", "videoDuration", "tem_duracao"]
    )
    categorical_predictors_comuns: list[str] = field(
        default_factory=lambda: ["type_raw", "dia_da_semana"]
    )
    # `videoPlayCount` (controle de alcance, ADR 0019 decisão 2) e
    # `paidPartnership` (via `isSponsored`) só existem para o grupo vídeo
    # (Reels) -- `isSponsored` nem existe no Bronze/Silver de posts estáticos.
    numeric_predictors_video: list[str] = field(
        default_factory=lambda: ["videoPlayCount", "paidPartnership"]
    )
    categorical_predictors_video: list[str] = field(default_factory=list)
    # `comprimento_legenda`/`Topic` (Tema) só existem para o grupo estático
    # (Posts) -- Reels não têm campo de caption no Bronze/Silver hoje
    # (limitação estrutural de dado coletado, não escolha de design; ver
    # `BRONZE_REELS_SCHEMA`/`SILVER_REELS_SCHEMA`, nenhum dos dois declara
    # `caption`/`hashtags`).
    numeric_predictors_estatico: list[str] = field(
        default_factory=lambda: ["comprimento_legenda"]
    )
    categorical_predictors_estatico: list[str] = field(default_factory=lambda: ["Topic"])


@dataclass
class ModelingConfig:
    pca: PCAConfig = field(default_factory=PCAConfig)
    # ADR 0020 (Ficha 2): PCA de posts do feed, features diferentes das de
    # reel. `cluster` (abaixo) é compartilhado entre reel e feed -- ambos os
    # PCAs sempre produzem as mesmas colunas de saída fixas
    # (PC1_Engajamento_videoPlay/PC2_videoDuration, ver `reduce_dimensions`),
    # então o `ClusterConfig` que as consome não precisa de uma cópia própria
    # para feed.
    pca_feed: FeedPCAConfig = field(default_factory=FeedPCAConfig)
    cluster: ClusterConfig = field(default_factory=ClusterConfig)
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)
    preprocessing: PreprocessingConfig = field(default_factory=PreprocessingConfig)
    topics: TopicModelConfig = field(default_factory=TopicModelConfig)
    post_topics: PostTopicModelConfig = field(default_factory=PostTopicModelConfig)
    # ADR 0020 (Ficha 4) / issue #89: BERTopic sobre legenda+transcrição.
    discourse_topics: DiscourseTopicModelConfig = field(
        default_factory=DiscourseTopicModelConfig
    )
    post_performance: PostPerformanceConfig = field(default_factory=PostPerformanceConfig)
    gold_clusters_path: Path = settings.GOLD_CLUSTERS
    gold_sentiment_path: Path = settings.GOLD_SENTIMENT
    # Tabela paralela de histórico (mode append) -- ver issue #52 / ADR 0017.
    gold_sentiment_history_path: Path = settings.GOLD_SENTIMENT_HISTORY
    # ADR 0020 (Ficha 4) / issue #89: tabela própria, separada de
    # `governor_sentiment` -- ver `GOLD_DISCOURSE_TOPICS_SCHEMA`.
    gold_discourse_topics_path: Path = settings.GOLD_DISCOURSE_TOPICS
    # ADR 0020 (Ficha 6) / issue #91: Score ICE de priorização de tópicos de
    # comentário, estágio pós-modelagem (mesma posição/dependência da NSM,
    # Ficha 5) -- ver `TopicPriorityScorer`.
    gold_topic_priority_score_path: Path = settings.GOLD_TOPIC_PRIORITY_SCORE
    # ADR 0020 (Ficha 5) / issue #90: North Star Metric (NSM) de engajamento
    # qualificado por perfil, mesma posição/dependência do Score ICE acima --
    # ver `NsmScorer`.
    gold_nsm_path: Path = settings.GOLD_NSM
    gold_post_performance_coefficients_path: Path = settings.GOLD_POST_PERFORMANCE_COEFFICIENTS
    gold_post_performance_predictions_path: Path = settings.GOLD_POST_PERFORMANCE_PREDICTIONS
    checkpoints_dir: Path = settings.MODEL_CHECKPOINTS_DIR
    logs_dir: Path = settings.LOGS_DIR


@dataclass
class GeminiRefinerConfig:
    api_key: str
    model: str = "gemini-2.0-flash"
    prompt_template: str | None = None
    sleep_seconds: int = 60
    sleep_every_n_topics: int = 10
    gold_sentiment_path: Path = settings.GOLD_SENTIMENT
    # ADR 0020 (Ficha 6) / issue #91: `topic_priority_score` é recalculado
    # junto do refinamento via Gemini (ver `refine_topics_with_gemini`) --
    # Score ICE depende de `governor_sentiment` já refinado, não dos
    # rótulos provisórios do estágio determinístico.
    gold_topic_priority_score_path: Path = settings.GOLD_TOPIC_PRIORITY_SCORE
