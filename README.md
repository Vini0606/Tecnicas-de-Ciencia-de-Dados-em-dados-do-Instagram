# Técnicas de NLP em Dados do Instagram

**Autor:** Vinícius de Paula R. Carvalho
**Versão do repositório:** atual (veja histórico de commits)
**Python mínimo suportado:** 3.10

Resumo: este repositório implementa um pipeline de extração e processamento de dados do Instagram (perfís, posts e reels) e expõe dashboards Streamlit que consomem tabelas Delta Lake organizadas em uma arquitetura Medallion (Bronze → Silver → Gold). Uma implementação legacy baseada em Excel (`data/processed/all.xlsx`) é mantida exclusivamente para compatibilidade com notebooks históricos.

---

## Sumário

1. [Visão geral](#visão-geral)
2. [Arquitetura (Medallion + Delta)](#arquitetura-medallion--delta)
3. [Fluxo de dados e pontos de entrada](#fluxo-de-dados-e-pontos-de-entrada)
4. [Estrutura de diretórios](#estrutura-de-diretórios)
5. [Repositórios de dados (`src/repositories`)](#repositórios-de-dados-srcrepositories)
6. [Configuração (`config/settings.py`)](#configuração-configsettingspy)
7. [Como executar (local)](#como-executar-local)
8. [Dashboards Streamlit](#dashboards-streamlit)
9. [Notebooks — estado e compatibilidade](#notebooks---estado-e-compatibilidade)
10. [Testes](#testes)
11. [Legado (`legacy/`)](#legado-legacy)
12. [Dependências e ambiente](#dependências-e-ambiente)
13. [Contribuição e manutenção](#contribuição-e-manutenção)

---

## Visão geral

O repositório centraliza a coleta, transformação e disponibilização de dados do Instagram para análise e visualização. A fonte de leitura ativa para os dashboards e análises é o conjunto de tabelas Delta Lake organizadas nas camadas Bronze, Silver e Gold. A versão baseada em Excel (`data/processed/all.xlsx`) é considerada LEGADO e somente usada para notebooks que não foram atualizados.

## Arquitetura (Medallion + Delta)

- Bronze: diretório local `data/bronze/` (configurável em `config/settings.py`) contendo dados brutos particionados por tipo (`instagram_profiles`, `instagram_posts`, `instagram_reels`).
- Silver: diretório local `data/silver/` com tabelas limpas e normalizadas (`profiles_clean`, `posts_clean`, `reels_clean`, `comments_clean`).
- Gold: diretório local `data/gold/` com tabelas agregadas e prontas para consumo (`governor_engagement`, `governor_sentiment`, `governor_topics`, `governor_clusters`).

Leitura principal: `src/repositories/delta_repository.py` usa `deltalake.DeltaTable` para carregar tabelas; é read-only e suporta `as_of_version` / `as_of_timestamp` para reproducibilidade.

## Fluxo de dados e pontos de entrada

- Extração: `src/data_extract/InstagramScraper` (usa `ApifyClient`) gera JSONs em `data/raw/` (`profiles.json`, `posts.json`, `reels.json`).
- Transformação: `src/features` aplica limpeza, explode comentários (`CommentsTransformer`) e calcula métricas de engajamento (`EngagementFeatureBuilder`).
- Carga (ativa): os DataFrames são persistidos em tabelas Delta na estrutura Medallion (Bronze→Silver→Gold). A escrita para Delta é feita por writers (não por `DeltaRepository`).
- Compatibilidade legada: `src/repositories/ExcelDataRepository` escreve/ler `data/processed/all.xlsx` apenas quando scripts/notebooks legados o exigem.

Pontos de entrada:
- `pipeline.py` — orquestrador local principal (executa extração condicional, transformação e gravação nas camadas Delta). Use para regenerar tabelas Delta.
- `app.py` / `pages/` — dashboards Streamlit que consomem `DeltaRepository`.

## Estrutura de diretórios (essencial)

Veja a organização principal do projeto (resumida):

- `app.py` — Streamlit root page
- `pipeline.py` — orquestrador ETL (local)
- `config/settings.py` — caminhos e parâmetros (medallion dirs, jsons, legacy xlsx)
- `src/` — código fonte (scraper, readers, features, repositories, visualization, analyzes)
- `pages/` — Streamlit pages (`01_exploratory.py`, `02_modeling.py`)
- `data/` — `raw/`, `bronze/`, `silver/`, `gold/`, `processed/` (legacy)
- `notebooks/` — análises históricas (algumas dependem de `all.xlsx`)
- `legacy/` — scripts legados (migrados; não são necessários para o fluxo ativo)

## Repositórios de dados (`src/repositories`)

- `DeltaRepository` — leitura somente (usa `deltalake.DeltaTable`). Métodos principais: `load_profiles()`, `load_posts()`, `load_reels()`, `load_comments()`, `load_clusters()`. Lança `FileNotFoundError` com instrução para executar o pipeline Medallion quando a tabela não existe.
- `ExcelDataRepository` — leitura/escrita para `all.xlsx`. Mantido para compatibilidade com notebooks legados.
- `S3DataRepository` — implementação cloud (Parquet sobre S3). Usada pelos lambdas ou deployment cloud.

### Observação importante
Os dashboards e testes do repositório devem usar `DeltaRepository` por padrão. `ExcelDataRepository` é considerado legacy e sua presença no `config` indica apenas um caminho de compatibilidade (`ALL_XLSX`).

## Configuração (`config/settings.py`)

As principais variáveis e caminhos (hoje):

- `DATA_DIR`: raiz dos dados (padrão `./data`)
- `RAW_DATA_DIR`: `DATA_DIR/raw`
- `PROCESSED_DATA_DIR`: `DATA_DIR/processed` (contém `all.xlsx` legado)
- `PROFILES_JSON`, `POSTS_JSON`, `REELS_JSON` — paths para JSONs brutos em `data/raw`
- `ALL_XLSX` — path legado para `data/processed/all.xlsx` (mantido por compatibilidade)
- Medallion dirs: `BRONZE_DIR`, `SILVER_DIR`, `GOLD_DIR` e nomes específicos das tabelas (ex.: `GOLD_ENGAGEMENT` = `gold/governor_engagement`)

Se for executar em cloud/CI, configure as variáveis de ambiente correspondentes (ex.: `S3_BUCKET`, `AWS_LAMBDA_FUNCTION_NAME` quando aplicável).

## Como executar (local)

Recomendações rápidas:

1) Instale dependências (venv recomendado):

```powershell
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
```

2) Regenerar tabelas Delta (executa ETL local):

```powershell
uv run python pipeline.py
```

3) Executar dashboards Streamlit (raiz do projeto):

```powershell
uv run streamlit run app.py
# ou abrir uma página específica
uv run streamlit run pages/01_exploratory.py
```

4) Testes unitários:

```powershell
uv run pytest -q
```

## Dashboards Streamlit

- `app.py` — define configuração global do Streamlit e texto inicial.
- `pages/01_exploratory.py` — Análise exploratória que consome `DeltaRepository.load_profiles()` e `load_reels()`.
- `pages/02_modeling.py` — Modelagem/NLP que consome comentários e tópicos a partir das tabelas Gold/Silver.

Dica: os scripts dos pages inserem a raiz do projeto no `sys.path` quando necessário para importar `src/` e `config/` corretamente dentro do ambiente do Streamlit.

## Notebooks — estado e compatibilidade

- Notebooks em `notebooks/` são históricos e muitos dependem de `data/processed/all.xlsx` (fluxo legado). Não é obrigatório rodá-los para ter o pipeline Delta funcionando.
- Se precisar reexecutar notebooks legados, gere `all.xlsx` via `legacy/pipeline_legacy.py` ou adapte os notebooks para consumir `DeltaRepository`.

## Testes

- Testes unitários e de integração estão em `tests/` (ex.: `test_repository.py` valida a leitura via `DeltaRepository`).
- Execute com `uv run pytest -q`.

## Legado (`legacy`)

Arquivos legados foram movidos para `legacy/`. Eles existem apenas para referência ou migração manual:

- `legacy/pipeline_legacy.py` — pipeline antigo que gera `data/processed/all.xlsx`.
- `legacy/migrate_to_medallion.py` — utilitário que tenta mover dados do Excel para tabelas Delta.

## Dependências e ambiente

- `deltalake` — leitura/escrita de tabelas Delta
- `pandas`, `numpy` — manipulação de dados
- `streamlit` — dashboards
- `pyarrow` — serialização Parquet/Delta

Consulte `requirements.txt` e `pyproject.toml` para a lista completa e versões.

## Contribuição e manutenção

- Prioridade: manter o fluxo Delta (Medallion) funcionando; alterações no Excel devem ser consideradas apenas para compatibilidade documental.
- Ao adicionar novas tabelas, registre corretamente o caminho em `config/settings.py` e adicione métodos correspondentes em `src/repositories/delta_repository.py`.

---

Se quiser, aplico agora pequenas atualizações nos notebooks e em `config/settings.py` para eliminar as últimas referências ativas ao Excel (ou manter um aviso claro). 

**Qualidade dos dados:**
- Inspeção com `.info()` e `.isnull()` para cada DataFrame
- Identificação de colunas com dados ausentes e candidatas à remoção (ex: `businessAddress` com apenas 1 entrada preenchida de 27)
- Conversões de tipo (ex: `isPinned` para `bool`)

**Análise univariada dos perfis:**
- Seguidores: média 719k, mediana 361k, desvio padrão 996k (CV de 138%) — forte assimetria positiva por outliers
- Seguidos: média 3.417, mediana 2.814 — estratégias muito diversas
- `% ENGAJAMENTO`: mediana 0.54, máximo 2.51 (um perfil gerou 2,5× mais interações que seus seguidores)
- `RECENCIA`: ao menos 75% dos governadores postaram no último dia da coleta
- `FREQUENCIA`: média 2.7 posts/dia, variando de 0.1 a 7.4

**Análise univariada dos reels:**
- Curtidas: média 6.763, mediana 2.208 — desempenho altamente assimétrico com picos de 246k
- `videoPlayCount`: métrica primária de alcance (mediana 67k); `videoViewCount` é descartada (>75% dos vídeos com valor 0)
- Duração: 50% dos vídeos entre 43 e 81 segundos; máximo de 900 segundos

**Análise univariada dos posts do feed:**
- Comentários: média 452, mediana 176, máximo 11.135
- Curtidas: média 7.061, mediana 1.961, máximo 246.802
- `videoPlayCount`: média 142k, mediana 67k, máximo 2,6M

**Análise categórica:**
- 100% dos perfis são verificados, públicos e não criados recentemente
- 63% utilizam perfil de criador de conteúdo (não empresarial)
- 70% classificados como `Politician` na categoria profissional

---

### `03_modelagem_hibrida.ipynb`

**Pré-requisito:** `all.xlsx` com aba `reels_latestComments` preenchida.

Este é o notebook central de NLP e Machine Learning. Aplica quatro técnicas de modelagem em sequência:

**Análise de Componentes Principais (PCA):**
- Redução dimensional das métricas numéricas dos perfis para visualização e pré-processamento do clustering
- Seleção de componentes que explicam o máximo de variância

**Clusterização automática (`AutoClusterHPO`):**
- Agrupa governadores por padrão de comportamento digital
- Testa KMeans, DBSCAN e Agglomerative Clustering com otimização TPE via Hyperopt
- Score combinado de Silhouette, Calinski-Harabasz e Davies-Bouldin
- Resultado: clusters de governadores com perfis de engajamento semelhantes

**Análise de Sentimentos:**
- Pré-processamento dos comentários (limpeza de emojis, stopwords, normalização)
- Classificação de cada comentário como positivo, negativo ou neutro
- Utiliza modelos da biblioteca `transformers` (Hugging Face), especificamente modelos pré-treinados para português
- Produz a coluna `sentiment_label` no DataFrame de comentários

**Modelagem de Tópicos (BERTopic):**
- Identifica os principais temas abordados nos comentários usando embeddings semânticos
- Gera o "Intertopic Distance Map" via UMAP para visualização das relações entre tópicos
- O tópico dominante (maior círculo no mapa) representa o tema mais recorrente no corpus
- Produz as colunas `Topic` e `Name` no DataFrame de comentários

**Saída:** DataFrame de comentários enriquecido com `sentiment_label`, `Topic` e `Name`, salvo de volta no `all.xlsx`.

---

### `04_analise_regressao.ipynb`

**Pré-requisito:** `all.xlsx` com métricas de engajamento calculadas.

Investiga relações causais entre variáveis de perfil e métricas de desempenho por meio de regressão. Analisa se variáveis como número de seguidores, frequência de postagem e recência impactam significativamente o percentual de engajamento.

---

### `05_visualizacao_e_conclusoes.ipynb`

**Pré-requisito:** `all.xlsx` com todos os dados de modelagem preenchidos.

Notebook de síntese e relatório final. Lê os dados processados e modelados, realiza análise descritiva final e gera visualizações consolidadas que comunicam as conclusões do projeto — incluindo os gráficos exportados para `reports/figures/`.

---

## 9. Infraestrutura serverless (`lambdas/`)

Cada Lambda representa uma etapa do pipeline ETL, projetadas para serem disparadas em sequência via **AWS EventBridge** (agendado) ou **API Gateway** (sob demanda).

### `lambdas/extract/handler.py`

**Gatilho:** EventBridge agendado ou evento manual com `{"links": [...]}`.

Instancia `InstagramScraper` com o token Apify lido de variáveis de ambiente, coleta dados dos perfis passados no evento e salva os três JSONs brutos no S3 em `raw/profiles.json`, `raw/posts.json` e `raw/reels.json`.

**Variáveis de ambiente necessárias:** `APIFY_API_TOKEN`, `S3_BUCKET`, `RESULTS_LIMIT` (opcional, padrão 30).

**Dependências mínimas** (`lambdas/extract/requirements.txt`): `apify-client`, `boto3`, `python-dotenv`, `pandas`.

---

### `lambdas/transform/handler.py`

**Gatilho:** conclusão da Lambda de extração (S3 event ou Step Functions).

Lê os três JSONs do S3, aplica `EngagementFeatureBuilder` e `CommentsTransformer`, e salva cinco arquivos Parquet no S3 em `processed/`: `profiles.parquet`, `posts.parquet`, `reels.parquet`, `comments.parquet`, `reels_posts.parquet`.

**Variáveis de ambiente necessárias:** `S3_BUCKET`, `RAW_PREFIX` (padrão `raw/`), `PROCESSED_PREFIX` (padrão `processed/`).

**Dependências mínimas:** `boto3`, `pandas`, `pyarrow`, `fastparquet`.

---

### `lambdas/load/handler.py`

**Gatilho:** conclusão da Lambda de transformação.

Lê os cinco Parquets do S3, consolida em um único arquivo Excel com múltiplas abas e salva de volta no S3 como `processed/all.xlsx`.

**Variáveis de ambiente necessárias:** `S3_BUCKET`, `PROCESSED_PREFIX`, `OUTPUT_KEY` (opcional).

**Dependências mínimas:** `boto3`, `pandas`, `openpyxl`, `pyarrow`.

> **Nota arquitetural:** quando o dashboard usa `S3DataRepository`, este Lambda é opcional — o dashboard lê os Parquets diretamente. O Load Lambda é útil para gerar o Excel consolidado para consumo humano (relatórios, Power BI).

---

## 10. Testes (`tests/`)

A suíte de testes usa **pytest** com **pytest-mock** e **pytest-cov**.

| Arquivo | O que testa |
|---|---|
| `test_engagement.py` | Verifica que `EngagementFeatureBuilder.build()` cria as colunas `TOTAL ENGAJAMENTO`, `% ENGAJAMENTO`, `RECENCIA` e `FREQUENCIA`, e que os valores de engajamento percentual não são negativos |
| `test_comments.py` | Verifica que `CommentsTransformer.transform()` filtra corretamente comentários com mais de 512 caracteres |
| `test_repository.py` | Verifica a leitura de dados via `DeltaRepository` nos caminhos Gold/Silver do Delta Lake. |
| `test_transform_lambda.py` | Mocka o `boto3.client` com respostas sequenciais e verifica que o handler da Lambda de transformação retorna `statusCode 200` com os arquivos Parquet esperados no body |
| `test_load_lambda.py` | Mocka o `boto3.client` com bytes Parquet e verifica que o handler da Lambda de carga retorna `statusCode 200` com o `output_key` no body |

**Cobertura de casos de erro:** cada Lambda tem um teste verificando que, na ausência de `S3_BUCKET`, o handler retorna `statusCode 400` imediatamente.

**Executar todos os testes:**
```bash
uv run pytest tests/ -v --cov=src --cov-report=term-missing
```

---

## 11. Configuração (`config/`)

### `config/settings.py`

Centraliza todas as configurações do projeto. Cada valor pode ser sobrescrito por variável de ambiente, tornando o projeto executável em contextos diferentes (local, Docker, Lambda) sem alterar código.

| Variável | Padrão | Descrição |
|---|---|---|
| `PROJECT_ROOT` | detectado automaticamente | Caminho absoluto para a raiz do projeto |
| `DATA_DIR` | `data/` | Diretório base de dados |
| `RAW_DATA_DIR` | `data/raw/` | Dados brutos (JSONs da API) |
| `PROCESSED_DATA_DIR` | `data/processed/` | Dados transformados |
| `GOVERNADORES_FILE` | `data/raw/governadores.xlsx` | Lista de perfis a coletar |
| `PROFILES_JSON` | `data/raw/profiles.json` | Dados brutos de perfis |
| `POSTS_JSON` | `data/raw/posts.json` | Dados brutos de posts |
| `REELS_JSON` | `data/raw/reels.json` | Dados brutos de reels |
| `ALL_XLSX` | `data/processed/all.xlsx` | Dataset processado consolidado |
| `RANDOM_STATE` | `42` | Semente para reprodutibilidade |
| `RESULTS_LIMIT` | `30` | Máximo de posts/reels por perfil na API |
| `S3_BUCKET` | `""` | Bucket S3 para ambiente cloud |
| `IS_CLOUD` | `False` | `True` se executando em AWS Lambda |
| `N_CLUSTERS_KMEANS` | `5` | Número inicial de clusters |
| `TSNE_PERPLEXITY` | `30` | Perplexidade do t-SNE |

---

## 12. Dados (`data/`)

```
data/
├── raw/
│   ├── .gitkeep             ← mantém o diretório versionado sem expor dados
│   ├── governadores.xlsx    ← lista de 27 governadores com nome, estado e link
│   ├── profiles.json        ← gerado pelo pipeline (não versionado)
│   ├── posts.json           ← gerado pelo pipeline (não versionado)
│   └── reels.json           ← gerado pelo pipeline (não versionado)
└── processed/
    └── all.xlsx             ← gerado pelo pipeline (não versionado)
```

### `governadores.xlsx`

Arquivo de entrada manual com as colunas:

| Coluna | Descrição |
|---|---|
| `Nome` | Nome completo do governador |
| `Estado` | Unidade federativa |
| `Link` | URL do perfil Instagram (ex: `https://www.instagram.com/fulano/`) |

### `all.xlsx` — estrutura das abas

| Aba | Conteúdo | Linhas aproximadas |
|---|---|---|
| `profiles` | Dados de perfil enriquecidos com métricas RFM-like | 27 |
| `posts` | Posts do feed com métricas de engajamento | ~810 |
| `reels` | Reels com métricas de reprodução e engajamento | ~810 |
| `reels_latestComments` | Comentários explodidos e normalizados | variável |
| `reels_posts` | União de posts e reels para análise combinada | ~1.620 |

---

## 13. Relatórios (`reports/`)

| Arquivo | Descrição |
|---|---|
| `Analises.pbix` | Dashboard Power BI com análises visuais dos dados |
| `Dicionário de Dados.xlsx` | Definição de cada coluna dos DataFrames produzidos |
| `Relatório de ETL.pdf` | Documentação técnica do pipeline de extração e transformação |
| `Análise de Modelagem Híbrida p_ TCC.pdf` | Relatório completo com resultados de PCA, clustering, sentimentos e tópicos |
| `figures/heatmap.png` | Heatmap de correlação exportado |
| `figures/hierarchical_Documents_and_Topics.png` | Hierarquia de tópicos do BERTopic |
| `figures/hierarchy.png` | Dendrograma de clustering hierárquico |
| `figures/intertopic_map.png` | Mapa de distância intertópica (UMAP) |
| `figures/sentiment_plots.png` | Distribuição de sentimentos por governador |

---

## 14. CI/CD (`.github/`)

### `.github/workflows/python-app.yml`

Pipeline de integração contínua executado a cada `push` ou `pull_request` na branch `main`.

**Etapas:**

1. `actions/checkout@v4` — clona o repositório
2. `actions/setup-python@v5` — instala Python 3.11
3. `pip install -e .[dev]` — instala dependências de produção e desenvolvimento
4. `pytest tests/ -v --cov=src --cov-report=term-missing` — executa todos os testes com relatório de cobertura
5. `ruff check src/` — lint de todo o código-fonte

> Para usar `uv` no CI (mais rápido), substituir o passo de instalação por `pip install uv && uv sync`.

---

## 15. Como rodar o projeto com uv

### Pré-requisitos

- Python 3.9 ou superior
- [uv](https://docs.astral.sh/uv/) instalado

**Instalar o uv** (caso ainda não tenha):

```bash
# macOS e Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Via pip (alternativa)
pip install uv
```

---

### Passo 1 — Clonar o repositório

```bash
git clone https://github.com/Vini0606/Tecnicas-de-NLP-em-dados-do-Instagram.git
cd "Tecnicas de NLP em dados do Instagram"
```

---

### Passo 2 — Criar o ambiente virtual e instalar dependências

O `uv` lê o `pyproject.toml` e o `uv.lock` para criar um ambiente completamente determinístico:

```bash
# Instala dependências de produção + desenvolvimento (recomendado para trabalho local)
uv sync --extra dev

# Apenas dependências de produção (sem pytest, ruff etc.)
uv sync
```

O ambiente virtual é criado automaticamente em `.venv/`.

> **Por que usar `uv sync` em vez de `pip install`?** O `uv sync` usa o `uv.lock` para instalar versões exatamente iguais às testadas pelo autor, garantindo que o ambiente seja idêntico independente da data de instalação.

---

### Passo 3 — Configurar variáveis de ambiente

```bash
# Copiar o template
cp .env.example .env

# Editar o .env com suas credenciais
nano .env   # ou use seu editor preferido
```

Conteúdo mínimo do `.env`:

```env
APIFY_API_TOKEN=seu_token_apify_aqui
DATA_DIR=data
RESULTS_LIMIT=30
```

Para obter um token Apify gratuito: [apify.com](https://apify.com) → criar conta → API & Integrations → Personal API tokens.

---

### Passo 4 — Verificar a instalação

```bash
# Confirma que o ambiente está correto e todos os módulos são importáveis
uv run python -c "from src.features.engagement import EngagementFeatureBuilder; print('OK')"
```

---

### Passo 5 — Executar os testes

```bash
# Todos os testes com relatório de cobertura
uv run pytest tests/ -v --cov=src --cov-report=term-missing

# Apenas um arquivo de teste
uv run pytest tests/test_engagement.py -v

# Com output detalhado em caso de falha
uv run pytest tests/ -v -s
```

---

### Passo 6 — Rodar o pipeline ETL

Este passo coleta dados da API Apify (requer token válido e custo de créditos Apify) e gera o `all.xlsx`:

```bash
uv run python pipeline.py
```

Se os arquivos JSON já existirem em `data/raw/`, a extração via API é pulada. Para forçar uma nova extração:

```python
# Dentro do pipeline.py (alterar o __main__):
run_pipeline(apify_api_token=token, links=links, results_limit=30, force_extract=True)
```

---

### Passo 7 — Executar os notebooks

```bash
# Instalar o Jupyter (já incluído nas dependências dev) e abrir
uv run jupyter notebook notebooks/

# Ou com JupyterLab
uv run jupyter lab notebooks/
```

Executar na ordem:
1. `01_extracao_e_limpeza_de_dados.ipynb`
2. `02_analise_exploratoria.ipynb`
3. `03_modelagem_hibrida.ipynb`
4. `04_analise_regressao.ipynb`
5. `05_visualizacao_e_conclusoes.ipynb`

---

### Passo 8 — Iniciar os dashboards

```bash
# Dashboard completo com navegação multi-página
uv run streamlit run app.py

# Ou uma página específica diretamente
uv run streamlit run pages/01_exploratory.py
uv run streamlit run pages/02_modeling.py
```

Acesse em: `http://localhost:8501`

> **Pré-requisito:** o arquivo `data/processed/all.xlsx` deve existir antes de abrir o dashboard. Rode o notebook 01 ou o `pipeline.py` primeiro.

---

### Passo 9 — Lint e formatação

```bash
# Verificar problemas de estilo e bugs
uv run ruff check src/

# Corrigir automaticamente o que for possível
uv run ruff check src/ --fix

# Formatar o código
uv run ruff format src/
```

---

### Referência rápida de comandos uv

| Tarefa | Comando |
|---|---|
| Criar/atualizar ambiente | `uv sync --extra dev` |
| Adicionar dependência de produção | `uv add nome-do-pacote` |
| Adicionar dependência de desenvolvimento | `uv add --dev nome-do-pacote` |
| Remover dependência | `uv remove nome-do-pacote` |
| Executar qualquer script | `uv run python script.py` |
| Executar pytest | `uv run pytest` |
| Executar Streamlit | `uv run streamlit run app.py` |
| Atualizar o lockfile | `uv lock --upgrade` |
| Ver dependências instaladas | `uv pip list` |
| Ativar manualmente o venv | `source .venv/bin/activate` (Linux/Mac) |

---

## 16. Variáveis de ambiente

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `APIFY_API_TOKEN` | Sim (para ETL) | — | Token de autenticação da API Apify |
| `DATA_DIR` | Não | `data` | Diretório raiz dos dados |
| `RESULTS_LIMIT` | Não | `30` | Limite de posts/reels por perfil |
| `RANDOM_STATE` | Não | `42` | Semente para reprodutibilidade |
| `S3_BUCKET` | Só em cloud | `""` | Nome do bucket AWS S3 |
| `RAW_PREFIX` | Não | `raw/` | Prefixo S3 para dados brutos |
| `PROCESSED_PREFIX` | Não | `processed/` | Prefixo S3 para dados processados |
| `OUTPUT_KEY` | Não | `processed/all.xlsx` | Chave S3 do Excel consolidado |
| `N_CLUSTERS_KMEANS` | Não | `5` | Número de clusters inicial |
| `TSNE_PERPLEXITY` | Não | `30` | Perplexidade para redução t-SNE |
| `AWS_LAMBDA_FUNCTION_NAME` | Não | — | Definida automaticamente pela AWS; detecta ambiente cloud |

---

## 17. Dependências

### Produção

| Pacote | Uso |
|---|---|
| `pandas` | Manipulação de DataFrames em todo o pipeline |
| `apify-client` | Comunicação com a API Apify para coleta de dados |
| `scikit-learn` | Pré-processamento, clustering, PCA, métricas |
| `transformers` | Modelos de linguagem pré-treinados (análise de sentimentos) |
| `torch` | Backend PyTorch para os modelos Hugging Face |
| `sentence-transformers` | Embeddings semânticos para BERTopic |
| `bertopic` | Modelagem de tópicos com embeddings e UMAP |
| `hyperopt` | Otimização de hiperparâmetros via TPE (AutoClusterHPO) |
| `streamlit` | Framework dos dashboards interativos |
| `plotly` | Gráficos interativos nos dashboards e notebooks |
| `matplotlib` / `seaborn` | Visualizações estáticas nos notebooks |
| `openpyxl` | Leitura e escrita de arquivos `.xlsx` |
| `boto3` | SDK AWS para comunicação com S3 nas Lambdas |
| `python-dotenv` | Carregamento do arquivo `.env` |
| `nltk` / `spacy` | Pré-processamento de texto (tokenização, stopwords) |
| `google-generativeai` | Integração com modelos generativos do Google |
| `emoji` | Processamento de emojis nos comentários |
| `tiktoken` / `sentencepiece` / `protobuf` | Dependências de tokenização dos modelos LLM |

### Desenvolvimento

| Pacote | Uso |
|---|---|
| `pytest` | Framework de testes |
| `pytest-mock` | Fixtures de mock para testes de Lambda |
| `pytest-cov` | Relatório de cobertura de código |
| `pandas-stubs` | Type stubs do pandas para IDE |
| `ruff` | Linter e formatter (substitui flake8, isort, black) |