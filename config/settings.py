# config/settings.py

from pathlib import Path

# 1. CAMINHOS PRINCIPAIS DO PROJETO
# Path(__file__) é o caminho para este arquivo (settings.py)
# .parent é a pasta 'config'
# .parent.parent é a raiz do projeto
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"
REPORTS_DIR = PROJECT_ROOT / "reports"
MODELS_DIR = PROJECT_ROOT / "models"

# 2. NOMES DE ARQUIVOS DE DADOS
GOVERNADORES_FILE = RAW_DATA_DIR / "governadores.xlsx"
PROFILES_JSON = RAW_DATA_DIR / 'profiles.json'
POSTS_JSON = RAW_DATA_DIR / 'posts.json'
REELS_JSON = RAW_DATA_DIR / 'reels.json'
DICIONARIO_XLSX = RAW_DATA_DIR / 'Dicionário de Dados.xlsx'
ALL_XLSX = PROCESSED_DATA_DIR / 'all.xlsx'

# 3. PARÂMETROS PARA MODELOS E ANÁLISES
# Usado para garantir reprodutibilidade nos modelos
RANDOM_STATE = 42

# Parâmetros para clusterização, por exemplo
N_CLUSTERS_KMEANS = 5
TSNE_PERPLEXITY = 30

# 4. NOMES DE COLUNAS IMPORTANTES (evita erros de digitação)
PROFILE_COLUMN = "@_perfil"
TEXT_COLUMN = "text"
DATE_COLUMN = "timestamp"
LINK_COLUMN = "Link"