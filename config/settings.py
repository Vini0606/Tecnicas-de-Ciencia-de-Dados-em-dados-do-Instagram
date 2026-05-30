# config/settings.py

import os
from pathlib import Path

# Detecta a raiz do projeto
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Diretórios de dados (podem ser sobrescritos por variáveis de ambiente)
DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# Arquivos principais
GOVERNADORES_FILE = Path(
    os.environ.get("GOVERNADORES_FILE", RAW_DATA_DIR / "governadores.xlsx")
)
PROFILES_JSON = Path(os.environ.get("PROFILES_JSON", RAW_DATA_DIR / "profiles.json"))
POSTS_JSON = Path(os.environ.get("POSTS_JSON", RAW_DATA_DIR / "posts.json"))
REELS_JSON = Path(os.environ.get("REELS_JSON", RAW_DATA_DIR / "reels.json"))
# Legacy Excel path used only for historic notebooks and backward compatibility.
ALL_XLSX = Path(os.environ.get("ALL_XLSX", PROCESSED_DATA_DIR / "all.xlsx"))

# Parâmetros de execução
RANDOM_STATE = int(os.environ.get("RANDOM_STATE", 42))
RESULTS_LIMIT = int(os.environ.get("RESULTS_LIMIT", 30))

# Cloud
S3_BUCKET = os.environ.get("S3_BUCKET", "")
IS_CLOUD = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

# Valores padrão adicionais
N_CLUSTERS_KMEANS = int(os.environ.get("N_CLUSTERS_KMEANS", 5))
TSNE_PERPLEXITY = int(os.environ.get("TSNE_PERPLEXITY", 30))

# Colunas frequentemente usadas
PROFILE_COLUMN = os.environ.get("PROFILE_COLUMN", "@_perfil")
TEXT_COLUMN = os.environ.get("TEXT_COLUMN", "text")
DATE_COLUMN = os.environ.get("DATE_COLUMN", "timestamp")
LINK_COLUMN = os.environ.get("LINK_COLUMN", "Link")

# ── Caminhos Medallion (Bronze / Silver / Gold)
BRONZE_DIR = DATA_DIR / "bronze"
BRONZE_PROFILES = BRONZE_DIR / "instagram_profiles"
BRONZE_POSTS = BRONZE_DIR / "instagram_posts"
BRONZE_REELS = BRONZE_DIR / "instagram_reels"

SILVER_DIR = DATA_DIR / "silver"
SILVER_PROFILES = SILVER_DIR / "profiles_clean"
SILVER_POSTS = SILVER_DIR / "posts_clean"
SILVER_REELS = SILVER_DIR / "reels_clean"
SILVER_COMMENTS = SILVER_DIR / "comments_clean"

GOLD_DIR = DATA_DIR / "gold"
GOLD_ENGAGEMENT = GOLD_DIR / "governor_engagement"
GOLD_SENTIMENT = GOLD_DIR / "governor_sentiment"
GOLD_TOPICS = GOLD_DIR / "governor_topics"
GOLD_CLUSTERS = GOLD_DIR / "governor_clusters"

# S3 prefixes (cloud)
S3_BRONZE_PREFIX = os.environ.get("S3_BRONZE_PREFIX", "bronze/")
S3_SILVER_PREFIX = os.environ.get("S3_SILVER_PREFIX", "silver/")
S3_GOLD_PREFIX = os.environ.get("S3_GOLD_PREFIX", "gold/")
