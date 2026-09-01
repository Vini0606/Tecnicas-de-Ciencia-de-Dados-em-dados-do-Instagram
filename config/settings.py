# config/settings.py

import os
from pathlib import Path

# Detecta a raiz do projeto
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Diretórios de dados (podem ser sobrescritos por variáveis de ambiente)
DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))
RAW_DATA_DIR = DATA_DIR / "raw"

# Dado de referência mantido manualmente (não gerado pelo pipeline, por isso
# fora de data/ -- essa árvore é ignorada/efêmera; ver ADR 0013).
REFERENCE_DIR = PROJECT_ROOT / "reference"

# Arquivos principais
GOVERNADORES_FILE = Path(
    os.environ.get("GOVERNADORES_FILE", REFERENCE_DIR / "governadores.xlsx")
)

# Parâmetros de execução
RANDOM_STATE = int(os.environ.get("RANDOM_STATE", 42))
RESULTS_LIMIT = int(os.environ.get("RESULTS_LIMIT", 30))

# Valores padrão adicionais
N_CLUSTERS_KMEANS = int(os.environ.get("N_CLUSTERS_KMEANS", 5))
TSNE_PERPLEXITY = int(os.environ.get("TSNE_PERPLEXITY", 30))

# Intervalo de auto-refresh (segundos) da página de monitoramento do
# dashboard (`pages/03_monitoring.py`) -- ver issue #50 / ADR 0016.
DASHBOARD_REFRESH_SECONDS = int(os.environ.get("DASHBOARD_REFRESH_SECONDS", 60))

# Colunas frequentemente usadas
PROFILE_COLUMN = os.environ.get("PROFILE_COLUMN", "@_perfil")
TEXT_COLUMN = os.environ.get("TEXT_COLUMN", "text")
DATE_COLUMN = os.environ.get("DATE_COLUMN", "timestamp")
LINK_COLUMN = os.environ.get("LINK_COLUMN", "Link")

# Landing zone: JSON bruto por entidade/run_id, sem schema, anterior à
# Bronze — arquiva fidelidade total contra a Bronze descartar campos fora
# do seu schema fixo (ver ADR 0011, decisão 1).
LANDING_DIR = DATA_DIR / "landing"

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
SILVER_GOVERNORS_METADATA = SILVER_DIR / "governors_metadata"

GOLD_DIR = DATA_DIR / "gold"
GOLD_ENGAGEMENT = GOLD_DIR / "governor_engagement"
# Tabela paralela de histórico (mesmo schema, modo append) -- só para
# engajamento por enquanto, ver ADR 0016. `governor_engagement` continua em
# overwrite, inalterada para os consumidores existentes.
GOLD_ENGAGEMENT_HISTORY = GOLD_DIR / "governor_engagement_history"
GOLD_SENTIMENT = GOLD_DIR / "governor_sentiment"
# Tabela paralela de histórico (mesmo schema, modo append) -- ver issue #52 /
# ADR 0017. `governor_sentiment` continua em overwrite, inalterada para os
# consumidores existentes.
GOLD_SENTIMENT_HISTORY = GOLD_DIR / "governor_sentiment_history"
GOLD_CLUSTERS = GOLD_DIR / "governor_clusters"
GOLD_PROFILE_CLUSTERS_ENGAGEMENT = GOLD_DIR / "governor_profile_clusters_engagement"

# Checkpoints locais do estágio determinístico de modelagem (ver ADR 0003) —
# não são Delta, ficam fora do git.
MODEL_CHECKPOINTS_DIR = DATA_DIR / "model_checkpoints"

# Logs estruturados por run_id (ver ADR 0015) -- separado de LANDING_DIR e
# MODEL_CHECKPOINTS_DIR de propósito: log operacional não é dado de negócio.
LOGS_DIR = DATA_DIR / "logs"
