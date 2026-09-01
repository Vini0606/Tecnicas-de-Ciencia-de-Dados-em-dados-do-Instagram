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
class ClusterConfig:
    feature_columns: list[str] = field(
        default_factory=lambda: ["PC1_Engajamento_videoPlay", "PC2_videoDuration"]
    )
    max_evals_per_algo: int = 100
    random_state: int = 42
    max_n_clusters: int | None = None


@dataclass
class SentimentConfig:
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
    nr_topics: int = 50
    calculate_probabilities: bool = True
    verbose: bool = True
    token_pattern: str = EMOJI_TOKEN_PATTERN


@dataclass
class ModelingConfig:
    pca: PCAConfig = field(default_factory=PCAConfig)
    cluster: ClusterConfig = field(default_factory=ClusterConfig)
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)
    preprocessing: PreprocessingConfig = field(default_factory=PreprocessingConfig)
    topics: TopicModelConfig = field(default_factory=TopicModelConfig)
    gold_clusters_path: Path = settings.GOLD_CLUSTERS
    gold_sentiment_path: Path = settings.GOLD_SENTIMENT
    # Tabela paralela de histórico (mode append) -- ver issue #52 / ADR 0017.
    gold_sentiment_history_path: Path = settings.GOLD_SENTIMENT_HISTORY
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
