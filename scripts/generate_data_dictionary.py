"""
Gera `reference/dicionario_de_dados_medallion.xlsx` -- catálogo de dados
detalhado de todas as tabelas Bronze/Silver/Gold da arquitetura Medallion.

Metadados técnicos (tabela, coluna, tipo, nullable) são extraídos direto de
`src/schemas_delta.py` -- a mesma fonte usada para validar contrato de dados
em runtime -- então a planilha nunca diverge do schema real por esquecimento
de atualização manual. Descrição de negócio, papel da coluna, linhagem e
status de cada tabela são curados manualmente neste script, a partir da
leitura dos módulos que escrevem cada camada (`src/features/*`,
`src/modeling/*`, `config/settings.py`).

Reexecutar após qualquer mudança em `src/schemas_delta.py` -- se uma coluna
nova não tiver descrição neste script, ela aparece na planilha com um
marcador `[SEM DESCRIÇÃO -- revisar scripts/generate_data_dictionary.py]`
em vez de ficar omitida silenciosamente.

Uso:
    uv run python scripts/generate_data_dictionary.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyarrow as pa
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from src import schemas_delta as sd

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "reference" / "dicionario_de_dados_medallion.xlsx"

MISSING_DESC = "[SEM DESCRIÇÃO -- revisar scripts/generate_data_dictionary.py]"

# ---------------------------------------------------------------------------
# 1. Metadados de tabela (camada, caminho, grão, escrita, leitura, status)
# ---------------------------------------------------------------------------

TABLES: list[dict] = [
    # ---------------------------- BRONZE --------------------------------
    {
        "camada": "Bronze",
        "tabela": "instagram_profiles",
        "schema": sd.BRONZE_PROFILES_SCHEMA,
        "caminho": "data/bronze/instagram_profiles",
        "grao": "Uma linha por resultado bruto do scraper Apify para um perfil de governador, por execução -- append-only, nada é sobrescrito nem deduplicado nesta camada.",
        "modo_escrita": "append",
        "escrito_por": "src/data_extract/bronze_writer.py (BronzeWriter.write_profiles), chamado por pipeline.py",
        "lido_por": "src/features/silver/profile_cleaner.py (ProfileCleaner.clean)",
        "status": "Produção",
        "adr": "ADR 0011 (landing zone/Bronze)",
        "descricao": "Metadados de perfil (seguidores, verificação, categoria de negócio) coletados via apify/instagram-scraper (ver aba Actors Apify), rodando em modo perfil (resultsType='details').",
        "notas": "Fidelidade total ao retorno do Apify -- nenhuma limpeza aqui; campos list/dict do Apify são serializados como JSON string (BronzeWriter._add_ingestion_metadata). Payload bruto arquivado em data/landing/<run_id>/profiles.json (ou /tmp/landing/... na Lambda) ANTES desta escrita -- ver aba Linhagem.",
    },
    {
        "camada": "Bronze",
        "tabela": "instagram_posts",
        "schema": sd.BRONZE_POSTS_SCHEMA,
        "caminho": "data/bronze/instagram_posts",
        "grao": "Uma linha por post de feed (imagem/vídeo/carrossel) retornado pelo scraper, por execução -- append-only.",
        "modo_escrita": "append",
        "escrito_por": "src/data_extract/bronze_writer.py (BronzeWriter.write_posts), chamado por pipeline.py",
        "lido_por": "src/features/silver/post_cleaner.py (PostCleaner.clean_posts)",
        "status": "Produção",
        "adr": "ADR 0011",
        "descricao": "Posts do feed do Instagram (não-Reels) dos 27 perfis, via apify/instagram-post-scraper (ver aba Actors Apify).",
        "notas": "Não tem campo de comentário embutido (latestComments) -- por isso governor_sentiment/comments_clean só cobrem comentário de Reels, nunca de post de feed. Payload bruto arquivado em data/landing/<run_id>/posts.json (ou /tmp/landing/... na Lambda) ANTES desta escrita -- ver aba Linhagem. Perfil sem NENHUM post próprio (0 itens, não confundir com perfil sem `id`) gera item de erro `{\"error\": \"no_items\", \"errorDescription\": \"Empty or private data...\"}` -- caso real (2026-09): claudiocastrorj (verificado, 2M+ seguidores) tinha só marcações de terceiros na grade, zero posts/reels próprios publicados.",
    },
    {
        "camada": "Bronze",
        "tabela": "instagram_reels",
        "schema": sd.BRONZE_REELS_SCHEMA,
        "caminho": "data/bronze/instagram_reels",
        "grao": "Uma linha por Reel retornado pelo scraper, por execução -- append-only.",
        "modo_escrita": "append",
        "escrito_por": "src/data_extract/bronze_writer.py (BronzeWriter.write_reels), chamado por pipeline.py",
        "lido_por": "src/features/silver/post_cleaner.py (PostCleaner.clean_reels), src/features/silver/comment_cleaner.py (CommentCleaner.clean)",
        "status": "Produção",
        "adr": "ADR 0011; ADR 0020 Ficha 3 / issue #88 (transcript)",
        "descricao": "Reels dos 27 perfis, via apify/instagram-reel-scraper (ver aba Actors Apify), incluindo os comentários mais recentes embutidos (latestComments) e, quando a flag paga includeTranscript está ativa, a transcrição de fala do vídeo.",
        "notas": "`transcript` é nullable e só vem preenchido quando a execução ligou explicitamente a flag paga do actor (custo por minuto de vídeo) -- não confundir ausência com 'sem fala'. Payload bruto arquivado em data/landing/<run_id>/reels.json (ou /tmp/landing/... na Lambda) ANTES desta escrita -- ver aba Linhagem. Mesma ressalva de instagram_posts sobre perfil com zero itens próprios (`error: 'no_items'`).",
    },
    {
        "camada": "Bronze",
        "tabela": "ugc_mentions (schema definido, ainda não materializado)",
        "schema": sd.BRONZE_UGC_MENTIONS_SCHEMA,
        "caminho": "config/settings.py::BRONZE_UGC_MENTIONS (data/bronze/ugc_mentions)",
        "grao": "Uma linha por post de TERCEIROS que marca/menciona o perfil do governador (nível 'Creating' do COBRA), por execução.",
        "modo_escrita": "append",
        "escrito_por": "src/data_extract/bronze_writer.py (BronzeWriter.write_ugc_mentions), chamado por scripts/run_ugc_mentions.py",
        "lido_por": "src/features/silver/ugc_mention_cleaner.py",
        "status": "Produção (ressalva) -- writer implementado e testado (2026-09-19), mas SEM execução real disparada ainda (custo Apify -- ver scripts/run_ugc_mentions.py)",
        "adr": "ADR 0020 Ficha 8 / issue #93",
        "descricao": "UGC (user-generated content) de terceiros mencionando/marcando o governador, via apify/instagram-tagged-scraper (ver aba Actors Apify -- status PILOTO).",
        "notas": "O piloto obrigatório da issue #93 (scripts/run_apify_mentions_pilot.py) rodou de verdade em 2026-09-19 contra os 26 perfis com Instagram rastreável (119 posts, data/pilot/mentions_pilot_20260919T030401Z.json) -- grava em data/pilot/*.json, FORA do Delta Lake, não passa pela landing zone nem por BronzeWriter. O schema abaixo foi CORRIGIDO a partir desse resultado real: `authorUsername`/`authorIsVerified`/`isPaidPartnership`/`isAd`/`isAffiliate`/`matchTypes` da especificação original (issue #93) NÃO existem no retorno do actor -- removidos/substituídos por `ownerUsername`/`ownerFullName`/`ownerId`/`paidPartnership`/`taggedUsers` (nomes reais). `scripts/run_ugc_mentions.py` (novo, 2026-09-19) fecha o loop Bronze->Silver->Gold sob o mesmo run_id, mesmo padrão de scripts/run_apify_backfill.py -- testado ponta a ponta (Delta real via tmp_path), mas nunca disparado contra a Apify de produção (custo real, decisão do usuário).",
    },
    # ---------------------------- SILVER --------------------------------
    {
        "camada": "Silver",
        "tabela": "profiles_clean",
        "schema": sd.SILVER_PROFILES_SCHEMA,
        "caminho": "data/silver/profiles_clean",
        "grao": "Uma linha por perfil de governador (deduplicado -- mantém só o registro mais recente por `id`).",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/silver/profile_cleaner.py (ProfileCleaner.clean/write)",
        "lido_por": "src/features/gold/engagement_aggregator.py; pages/*",
        "status": "Produção",
        "adr": "ADR 0011",
        "descricao": "Perfis conformados ao contrato Silver: tipos fechados (int32/bool não-nulos), colunas de baixo valor analítico descartadas (biografia, URLs de foto, endereço de negócio).",
        "notas": "Linha sem `id` é descartada (não quebra a escrita da tabela inteira) E gera um `logger.warning` com o(s) username(s) afetado(s) -- achado real: o link morto do Espírito Santo (PR #132) gerava esse descarte silenciosamente até ser descoberto manualmente; `fullName` ausente cai para `username`, depois `inputUrl`, nunca fica nulo por acidente.",
    },
    {
        "camada": "Silver",
        "tabela": "posts_clean",
        "schema": sd.SILVER_POSTS_SCHEMA,
        "caminho": "data/silver/posts_clean",
        "grao": "Uma linha por post de feed, deduplicado por `id`.",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/silver/post_cleaner.py (PostCleaner.clean_posts/write_posts)",
        "lido_por": "src/features/gold/engagement_aggregator.py; src/modeling/post_performance.py (grupo estático); pages/*",
        "status": "Produção",
        "adr": "ADR 0011; ADR 0019 parte A (hashtags/type_raw)",
        "descricao": "Posts de feed conformados: timestamp do Apify parseado para `data_hora` (fuso America/Sao_Paulo), `Tipo` fixado em 'FEED'.",
        "notas": "`caption`/`hashtags` são preservados aqui (mas não em reels_clean) -- Reels não têm campo de legenda coletado, limitação estrutural de dado, não de design. Linha sem `id` é descartada e gera `logger.warning` (mesmo tratamento de profiles_clean).",
    },
    {
        "camada": "Silver",
        "tabela": "reels_clean",
        "schema": sd.SILVER_REELS_SCHEMA,
        "caminho": "data/silver/reels_clean",
        "grao": "Uma linha por Reel, deduplicado por `id`.",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/silver/post_cleaner.py (PostCleaner.clean_reels/write_reels)",
        "lido_por": "src/features/gold/engagement_aggregator.py; src/modeling (PCA/clustering); src/modeling/post_performance.py (grupo vídeo); pages/*",
        "status": "Produção",
        "adr": "ADR 0011; ADR 0019 parte A; ADR 0020 Ficha 3 / issue #88 (transcript)",
        "descricao": "Reels conformados: `Tipo` fixado em 'REELS', `Total de Engajamento` pré-calculado (likes+comentários), `transcript` propagado sem transformação.",
        "notas": "`Total de Engajamento` aqui é por-reel (insumo do PCA/AutoClusterHPO) -- não confundir com `TOTAL ENGAJAMENTO` (maiúsculo, com espaço) de governor_engagement, que é por-perfil agregado. Linha sem `id` é descartada e gera `logger.warning` (mesmo tratamento de profiles_clean).",
    },
    {
        "camada": "Silver",
        "tabela": "comments_clean",
        "schema": sd.SILVER_COMMENTS_SCHEMA,
        "caminho": "data/silver/comments_clean",
        "grao": "Uma linha por comentário individual, explodido a partir de `latestComments` (Bronze reels) e deduplicado por `id_comment`.",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/silver/comment_cleaner.py (CommentCleaner.clean/write)",
        "lido_por": "src/modeling (análise de sentimento, BERTopic); src/dashboard/loaders.py (fallback quando governor_sentiment ainda não existe)",
        "status": "Produção",
        "adr": "ADR 0011",
        "descricao": "Comentários de Reels explodidos de dentro do JSON `latestComments`, filtrados a menos de 512 caracteres.",
        "notas": "Deriva EXCLUSIVAMENTE de Reels -- posts de feed não carregam comentário embutido no dado coletado, então não existe 'comentário de post' em nenhuma tabela do projeto.",
    },
    {
        "camada": "Silver",
        "tabela": "governors_metadata",
        "schema": sd.SILVER_GOVERNORS_METADATA_SCHEMA,
        "caminho": "data/silver/governors_metadata",
        "grao": "Uma linha por governador COM Instagram rastreável, deduplicada por `inputUrl` -- governador sem `Link` na planilha (célula em branco) não gera linha aqui.",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/silver/governors_metadata_cleaner.py (GovernorsMetadataCleaner.clean/write)",
        "lido_por": "src/dashboard/filters.py (nome/UF/partido, seletor de governador)",
        "status": "Produção (26 de 27 governadores -- ver notas)",
        "adr": "—",
        "descricao": "Dimensão de governador (nome, UF, partido) ingerida de reference/governadores.xlsx -- fonte única de verdade para o dashboard em vez de ler a planilha bruta a cada carregamento.",
        "notas": "`reference/governadores.xlsx` é mantido manualmente, fora do pipeline (ADR 0013) -- esta é a ÚNICA leitura de Excel que resta no projeto, e é de configuração, não de dado coletado. Governador sem Instagram rastreável (`Link` em branco) é descartado ANTES do cast para string, para não virar o texto literal 'nan' em `inputUrl` (NOT NULL, chave de junção do pipeline inteiro) -- mesmo filtro em scripts/apify_backfill_shared.py::load_links(). Caso real (2026-09): Rio de Janeiro fica sem Instagram rastreável desde a renúncia de Cláudio Castro (2026-03-23) -- o titular interino (desembargador Ricardo Couto, presidente do TJ-RJ) não tem perfil público de gestão. governors_metadata/Bronze/Silver/Gold refletem 26 governadores enquanto essa situação persistir.",
    },
    {
        "camada": "Silver",
        "tabela": "ugc_mentions (schema definido, ainda não materializado)",
        "schema": sd.SILVER_UGC_MENTIONS_SCHEMA,
        "caminho": "config/settings.py::SILVER_UGC_MENTIONS (data/silver/ugc_mentions)",
        "grao": "Uma linha por post de UGC, com `governor_username` já resolvido e `authorUsername` já normalizado.",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/silver/ugc_mention_cleaner.py (UGCMentionCleaner), chamado por scripts/run_ugc_mentions.py",
        "lido_por": "src/features/gold/ugc_mentions_aggregator.py, chamado por scripts/run_ugc_mentions.py",
        "status": "Produção (ressalva) -- mesma ressalva da Bronze ugc_mentions",
        "adr": "ADR 0020 Ficha 8 / issue #93",
        "descricao": "UGC de terceiros já limpo: `governor_username` derivado de `mentions` E `taggedUsers` (Bronze) cruzados com a lista de usernames conhecidos; `authorUsername` normaliza o handle do autor terceiro (na prática, sempre a partir de `ownerUsername` -- ver Bronze).",
        "notas": "`id`/`shortCode` são nullable aqui (ao contrário do padrão NOT NULL de profiles/posts/reels) porque o piloto ainda não confirmou presença garantida de `id` no actor escolhido -- o cleaner descarta linha sem os dois. Piloto real (2026-09-19) confirmou que checar só `mentions` perderia ~69% dos posts correlacionáveis -- a maioria só tem a marcação visual em `taggedUsers`, não @-menção em texto.",
    },
    # ----------------------------- GOLD ----------------------------------
    {
        "camada": "Gold",
        "tabela": "governor_engagement",
        "schema": sd.GOLD_ENGAGEMENT_SCHEMA,
        "caminho": "data/gold/governor_engagement",
        "grao": "Uma linha por perfil de governador -- snapshot agregado da execução mais recente.",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/gold/engagement_aggregator.py (EngagementAggregator)",
        "lido_por": "pages/*; src/modeling/post_performance.py; src/features/gold/nsm_scorer.py",
        "status": "Produção (LIMITAÇÃO CONHECIDA -- ver notas: governador removido de governadores.xlsx continua aparecendo aqui)",
        "adr": "ADR 0018",
        "descricao": "Métricas de engajamento por perfil: total ponderado, taxa sobre seguidores, recência e frequência de publicação.",
        "notas": "Sempre sobrescrita por completo a cada execução -- para série temporal, ver governor_engagement_history. LIMITAÇÃO CONHECIDA (2026-09-19): EngagementAggregator recalcula a partir de profiles_clean/posts_clean/reels_clean (Silver, que por sua vez vem de TODA a Bronze acumulada) -- não filtra contra governors_metadata/governadores.xlsx. Um governador removido da planilha (ex.: Rio de Janeiro/claudiocastrorj, sem Instagram rastreável desde 2026-03 -- ver PR #136) continua reaparecendo aqui indefinidamente, com o último snapshot real da Bronze (cada vez mais desatualizado) só recebendo um `_generated_at` novo a cada execução -- parece fresco, mas o dado por trás não é. Não afeta o seletor de governador do dashboard (vem de governors_metadata, filtra corretamente), mas PODE vazar como 'par' em telas que comparam perfis por cluster (ex.: Tela 4, via governor_profile_clusters_engagement, mesma limitação -- ver notas daquela tabela). Correção exigiria EngagementAggregator/estágio de modelagem cruzarem contra governors_metadata antes de processar -- fora de escopo até aqui, fica para decisão futura.",
    },
    {
        "camada": "Gold",
        "tabela": "governor_engagement_history",
        "schema": sd.GOLD_ENGAGEMENT_SCHEMA,
        "caminho": "data/gold/governor_engagement_history",
        "grao": "Uma linha por perfil POR EXECUÇÃO do pipeline (mesmo schema de governor_engagement, mas em modo append) -- histórico acumulado ao longo do tempo.",
        "modo_escrita": "append",
        "escrito_por": "src/features/gold/engagement_aggregator.py (mesmo EngagementAggregator, path diferente)",
        "lido_por": "src/modeling/growth_history.py (CMGR); pages/03_performance.py (auto-refresh)",
        "status": "Produção (histórico ainda curto -- ver governor_growth_metrics)",
        "adr": "ADR 0016",
        "descricao": "Base de série temporal de engajamento -- permite calcular tendência/crescimento sem reprocessar Bronze/Silver.",
        "notas": "Nunca sobrescrita nem deduplicada por execução -- cresce indefinidamente; governor_engagement (sem sufixo) continua em overwrite para não quebrar consumidores existentes.",
    },
    {
        "camada": "Gold",
        "tabela": "governor_sentiment",
        "schema": sd.GOLD_SENTIMENT_SCHEMA,
        "caminho": "data/gold/governor_sentiment",
        "grao": "Uma linha por texto avaliado (comentário, legenda ou transcrição) -- granularidade mista, discriminada pela coluna `fonte`.",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/gold/model_enricher.py (ModelEnricher.write_sentiment), a partir de src/modeling/sentiment.py + BERTopic",
        "lido_por": "pages/02_insights.py; src/features/gold/nsm_scorer.py; src/features/gold/topic_priority_scorer.py; scripts/refine_topics.py",
        "status": "Produção",
        "adr": "ADR 0019 (Topic/Name determinístico); ADR 0020 Ficha 3 / issue #88 (coluna fonte)",
        "descricao": "Sentimento (cardiffnlp/twitter-xlm-roberta-base-sentiment) e tópico BERTopic por texto avaliado.",
        "notas": "`scripts/refine_topics.py` reescreve os rótulos de `Name` via Gemini sobre esta MESMA tabela (não gera nova medição de sentimento) -- ver ADR 0001. NSM e Score ICE filtram só `fonte == 'comentario'`; linhas de legenda/transcrição não entram nessas duas métricas.",
    },
    {
        "camada": "Gold",
        "tabela": "governor_sentiment_history",
        "schema": sd.GOLD_SENTIMENT_SCHEMA,
        "caminho": "data/gold/governor_sentiment_history",
        "grao": "Uma linha por comentário/legenda/transcrição POR EXECUÇÃO de modelagem (mesmo schema de governor_sentiment, em modo append).",
        "modo_escrita": "append",
        "escrito_por": "src/features/gold/model_enricher.py (mesmo ModelEnricher, path diferente)",
        "lido_por": "src/modeling/growth_history.py (retenção de sentimento positivo)",
        "status": "Produção (histórico ainda curto)",
        "adr": "ADR 0017 / issue #52",
        "descricao": "Base de série temporal de sentimento -- alimenta a retenção de sentimento positivo do CMGR/Ficha 7.",
        "notas": "Mesma ressalva de granularidade mista de governor_sentiment (comentário/legenda/transcrição via `fonte`).",
    },
    {
        "camada": "Gold",
        "tabela": "governor_discourse_topics",
        "schema": sd.GOLD_DISCOURSE_TOPICS_SCHEMA,
        "caminho": "data/gold/governor_discourse_topics",
        "grao": "Uma linha por legenda/transcrição avaliada pelo BERTopic de discurso oficial.",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/gold/model_enricher.py (ModelEnricher.write_discourse_topics)",
        "lido_por": "dashboard/screens/{resumo,produzir,discurso_reacao,funil}.py (ADR 0021)",
        "status": "Produção",
        "adr": "ADR 0020 Ficha 4 / issue #89",
        "descricao": "Tópicos do que a ASSESSORIA publica (legenda de post/reel + transcrição de fala) -- BERTopic próprio, não misturado ao de comentário.",
        "notas": "Conceitualmente distinta de governor_sentiment: fala da assessoria (aqui) vs. reação do público (lá). Nunca comparar os `Topic`/`Name` das duas tabelas como se fossem o mesmo espaço de tópicos.",
    },
    {
        "camada": "Gold",
        "tabela": "governor_clusters",
        "schema": sd.GOLD_CLUSTERS_SCHEMA,
        "caminho": "data/gold/governor_clusters",
        "grao": "Uma linha por Reel OU post de feed (discriminado por `content_type`) -- clusterização de CONTEÚDO, não de perfil.",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/gold/model_enricher.py (ModelEnricher.write_clusters), a partir de src/modeling/clustering.py (AutoClusterHPO)",
        "lido_por": "dashboard/screens/{resumo,produzir,funil}.py (ADR 0021)",
        "status": "Produção",
        "adr": "ADR 0020 Ficha 2 / issue #87 (content_type)",
        "descricao": "Cluster de engajamento/duração por post (PCA -> KMeans/DBSCAN/Agglomerative via AutoClusterHPO, algoritmo eleito por score CVI combinado).",
        "notas": "`cluster_label = -1` é ruído do DBSCAN, não um cluster de negócio (ver seção 2.2 do README) -- nunca a mesma coisa que clusterização de PERFIL (governor_profile_clusters_engagement, tabela separada).",
    },
    {
        "camada": "Gold",
        "tabela": "governor_profile_clusters_engagement",
        "schema": sd.GOLD_PROFILE_CLUSTERS_ENGAGEMENT_SCHEMA,
        "caminho": "data/gold/governor_profile_clusters_engagement",
        "grao": "Uma linha por GOVERNADOR (não por post) -- clusterização de PERFIL por padrão de engajamento.",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/gold/model_enricher.py (ModelEnricher.write_profile_clusters_engagement), via src/modeling/orchestration.py::run_deterministic_modeling (pipeline.py --run-modeling / scripts/run_modeling.py) ou, isoladamente, via scripts/run_profile_clustering_engagement.py",
        "lido_por": "dashboard/screens/comparar.py (Tela 4 \"Comparar perfis\", ADR 0021 -- comparação de perfil vs. pares do mesmo cluster)",
        "status": "Produção (LIMITAÇÃO CONHECIDA -- herda de governor_engagement, ver notas)",
        "adr": "ADR 0020 Fase 2 / issue #86; ADR 0004/0005 (schema próprio, não genérico)",
        "descricao": "Agrupa governadores por semelhança de padrão de engajamento (mesma pipeline PCA->AutoClusterHPO do nível de conteúdo, mas features agregadas por perfil).",
        "notas": "Roda pós-Gold-de-engajamento (lê governor_engagement), dentro do mesmo estágio determinístico das demais tabelas de modelagem -- na Lambda serverless, é a etapa `model`, disparada depois de `load` (ver seção 3 do README). LIMITAÇÃO CONHECIDA (2026-09-19): como lê governor_engagement (que não filtra contra governadores.xlsx atual -- ver notas daquela tabela), um governador removido da planilha continua recebendo `cluster_perfil_engajamento` aqui e PODE aparecer como 'par' na Tela 4 (Comparar perfis) para outro governador do mesmo cluster, com dado cada vez mais desatualizado. Caso real: claudiocastrorj (RJ, sem Instagram rastreável desde 2026-03 -- PR #136).",
    },
    {
        "camada": "Gold",
        "tabela": "post_performance_coefficients",
        "schema": sd.GOLD_POST_PERFORMANCE_COEFFICIENTS_SCHEMA,
        "caminho": "data/gold/post_performance_coefficients",
        "grao": "Uma linha por preditor por grupo (vídeo/estático) por execução -- formato longo.",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/gold/model_enricher.py (write_post_performance_coefficients), a partir de src/modeling/post_performance.py (LassoCV)",
        "lido_por": "pages/03_performance.py (comparação entre governadores, coeficientes da regressão) -- órfã desde a ADR 0021, sem entrypoint ativo (ver seção 4 do README)",
        "status": "Produção",
        "adr": "ADR 0019 parte C",
        "descricao": "Coeficientes e R² (treino/holdout) da regressão Lasso que explica performance-por-post, separada em grupo vídeo (Reels) e estático (posts de imagem/carrossel) por terem preditores distintos (ex.: duração de vídeo só existe no grupo vídeo).",
        "notas": "`preditor` inclui, entre outros: hora_do_dia, dia_da_semana, tem_duracao, videoDuration (grupo vídeo), comprimento_legenda e Tema/Topic do BERTopic sobre legenda (grupo estático), paidPartnership (grupo vídeo). `r2_holdout` é nulo só no caso degenerado de um grupo sem governador em holdout.",
    },
    {
        "camada": "Gold",
        "tabela": "post_performance_predictions",
        "schema": sd.GOLD_POST_PERFORMANCE_PREDICTIONS_SCHEMA,
        "caminho": "data/gold/post_performance_predictions",
        "grao": "Uma linha por post individual (treino + holdout juntos, discriminados implicitamente pelo pipeline que os gerou).",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/gold/model_enricher.py (write_post_performance_predictions)",
        "lido_por": "pages/03_performance.py (dispersão previsto vs. real, resíduos) -- órfã desde a ADR 0021, sem entrypoint ativo (ver seção 4 do README)",
        "status": "Produção",
        "adr": "ADR 0019 parte C, decisão 9",
        "descricao": "Y real, Y previsto e resíduo por post -- Y = (likesCount + commentsCount × _WC_COMENTARIO) / followersCount, a mesma lógica de taxa ponderada de governor_engagement.% ENGAJAMENTO, mas por post em vez de agregada por perfil.",
        "notas": "Habilita a 'lacuna de execução' do dashboard (issue E da ADR 0019) sem precisar de uma tabela extra só para holdout.",
    },
    {
        "camada": "Gold",
        "tabela": "topic_priority_score",
        "schema": sd.GOLD_TOPIC_PRIORITY_SCORE_SCHEMA,
        "caminho": "data/gold/topic_priority_score",
        "grao": "Uma linha por tópico de COMENTÁRIO (ranking global, não por governador).",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/gold/topic_priority_scorer.py (TopicPriorityScorer)",
        "lido_por": "dashboard/screens/{resumo,produzir,radar}.py (priorização do que produzir a seguir, ADR 0021)",
        "status": "Produção",
        "adr": "ADR 0020 Ficha 6 / issue #91",
        "descricao": "Score ICE (Impacto x Confiança x Facilidade) de priorização de tópicos de comentário -- responde 'sobre o que o governador deveria produzir a seguir'.",
        "notas": "'Facilidade' é fixa em 1.0 nesta v1 (FACILIDADE_V1) -- não há dado de custo de produção real para calibrar, decisão deliberada em vez de inventar uma heurística sem lastro. 'alcance_topico' é proxy (likes+replies do comentário), não alcance/views real.",
    },
    {
        "camada": "Gold",
        "tabela": "governor_nsm",
        "schema": sd.GOLD_NSM_SCHEMA,
        "caminho": "data/gold/governor_nsm",
        "grao": "Uma linha por perfil de governador.",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/gold/nsm_scorer.py (NsmScorer)",
        "lido_por": "dashboard/screens/resumo.py (Tela 1, ADR 0021)",
        "status": "Produção -- verificado com dado real dos 27 perfis (ver notas)",
        "adr": "ADR 0020 Ficha 5 / issue #90",
        "descricao": "North Star Metric: (comentários positivos / comentários totais) × alcance médio -- engajamento qualificado por QUALIDADE de reação, não só volume.",
        "notas": "'alcance_medio' é proxy (TOTAL ENGAJAMENTO / count de governor_engagement), não alcance/views real -- Instagram não expõe alcance real para posts estáticos. Critério de aceite da issue #90 (ranking NSM inverter o ranking por engajamento bruto em pelo menos 1 caso real) confirmado em 2026-09-19 contra os 27 perfis reais: 25 dos 27 mudam de posição entre os dois rankings, inclusive o 1º lugar (tarcisiogdf ultrapassa romeuzemaoficial). Ver ADR 0020, Ficha 5, para o detalhe completo.",
    },
    {
        "camada": "Gold",
        "tabela": "governor_ugc_mentions (schema definido, ainda não materializado)",
        "schema": sd.GOLD_UGC_MENTIONS_SCHEMA,
        "caminho": "config/settings.py::GOLD_UGC_MENTIONS (data/gold/governor_ugc_mentions)",
        "grao": "Uma linha por post de UGC (grão fino -- agregação por governador é uma view em memória, não persistida).",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/gold/ugc_mentions_aggregator.py (GovernorUGCAggregator), chamado por scripts/run_ugc_mentions.py",
        "lido_por": "Nenhum consumidor de produção hoje -- dashboard/screens/funil.py (Tela 6, ADR 0021) proíbe estruturalmente qualquer referência a esta tabela (ver teste test_funil_module_never_references_ugc_tables); src/dashboard/filters.py tem a função de agregação, mas não é chamada por nenhuma tela atual",
        "status": "Produção (ressalva) -- mesma ressalva de Bronze/Silver ugc_mentions",
        "adr": "ADR 0020 Ficha 8 / issue #93",
        "descricao": "UGC orgânico vs. publi paga por post, com `is_organic` derivado de `paidPartnership` -- separa apoio espontâneo de publi paga ANTES de qualquer agregação.",
        "notas": "`GovernorUGCAggregator.aggregate_by_governor` (a 'view' de contagem/engajamento médio por governador) nunca expõe `authorUsername` individual no agregado, por desenho -- privacidade de quem menciona o governador, não só do próprio governador. Piloto real (2026-09-19) confirmou que `paidPartnership` é o único campo de publi que o actor expõe -- `isAd`/`isAffiliate` não existem como conceitos distintos, removidos do schema.",
    },
    {
        "camada": "Gold",
        "tabela": "governor_growth_metrics",
        "schema": sd.GOLD_GROWTH_METRICS_SCHEMA,
        "caminho": "data/gold/governor_growth_metrics",
        "grao": "Uma linha por perfil de governador -- snapshot recalculável a partir do histórico acumulado (sempre overwrite, nunca append).",
        "modo_escrita": "overwrite",
        "escrito_por": "src/features/gold/model_enricher.py (write_growth_metrics), via scripts/run_growth_metrics.py e src/modeling/growth_history.py",
        "lido_por": "Nenhuma tela do dashboard atual (ADR 0021) consome esta tabela -- dashboard/core/data.py::load_growth_metrics() existe, mas não é chamada por nenhuma das 6 telas",
        "status": "PRODUÇÃO, mas resultado marcado ILUSTRATIVO (ver notas) -- não sustenta conclusão definitiva ainda",
        "adr": "ADR 0020 Ficha 7 / issue #92",
        "descricao": "CMGR (crescimento mensal composto de seguidores) e retenção de sentimento positivo, calculados sobre governor_engagement_history/governor_sentiment_history.",
        "notas": "`cmgr_confiavel`/`retencao_confiavel` são False sempre que houver menos de MIN_PERIODS_CONFIAVEL=6 execuções mensais acumuladas -- em 2026-09 o pipeline ainda não acumulou histórico suficiente, então os valores validam a FÓRMULA, não sustentam conclusão real sobre crescimento dos perfis. `motivo`/`nota` explicam o porquê sempre que o valor for NaN ou não confiável.",
    },
]

# ---------------------------------------------------------------------------
# 1.5 Actors Apify -- origem detalhada de cada extração (quem raspa o quê,
# com quais parâmetros, e com que confiabilidade de fonte). Curado a partir
# de src/data_extract/scraper.py (ScraperConfig -- fonte de verdade dos IDs/
# parâmetros REALMENTE usados em produção) cruzado com
# docs/research/apify-instagram-actors-cobra-mapping.md (pesquisa de
# preço/adoção/schema, consultada direto na Apify Store e API pública em
# 2026-09-08 -- não re-verificada aqui, só citada).
# ---------------------------------------------------------------------------

APIFY_ACTORS: list[dict] = [
    {
        "papel": "Perfis (instagram_profiles)",
        "actor_slug": "apify/instagram-scraper",
        "actor_id": "shu8hvrXbJbY3Eb9W",
        "dev": "Apify (oficial)",
        "status": "Produção",
        "parametros_producao": "directUrls=<links>, addParentData=False, resultsLimit=100, resultsType='details', searchType='user' (src/data_extract/scraper.py::InstagramScraper.scrape_profiles).",
        "confiabilidade": "ID confirmado via api.apify.com/v2/acts/shu8hvrXbJbY3Eb9W -> {\"name\":\"instagram-scraper\",\"username\":\"apify\"} (docs/research/..., §0).",
        "notas": "É o actor GENÉRICO \"canivete suíço\" da Apify, não o dedicado apify/instagram-profile-scraper -- rodado só em resultsType='details' hoje. O mesmo actor/ID também suporta resultsType='mentions'/'comments' e busca por hashtag, não explorado no pipeline atual (ver docs/research/..., §7.3, para a rota de UGC que reaproveitaria este mesmo actor sem integrar um novo).",
    },
    {
        "papel": "Posts de feed (instagram_posts)",
        "actor_slug": "apify/instagram-post-scraper",
        "actor_id": "(resolvido pelo slug pela Apify -- não fixado como ID literal no código)",
        "dev": "Apify (oficial)",
        "status": "Produção",
        "parametros_producao": "username=<usernames>, resultsLimit=30 (ScraperConfig.results_limit) + extra_run_input opcional (ex.: onlyPostsNewerThan, usado por scripts/run_apify_backfill.py para recorte incremental).",
        "confiabilidade": "Confirmado via página do actor + input-schema (docs/research/..., §1.1) -- pay-per-event, ~$1.00/1.000 posts.",
        "notas": "Não tem includeTranscript nem includeSharesCount (esses são do reel-scraper) -- não confundir com o actor genérico usado para perfis.",
    },
    {
        "papel": "Reels (instagram_reels)",
        "actor_slug": "apify/instagram-reel-scraper",
        "actor_id": "(resolvido pelo slug pela Apify -- não fixado como ID literal no código)",
        "dev": "Apify (oficial)",
        "status": "Produção",
        "parametros_producao": "username=<usernames>, resultsLimit=30 + includeTranscript=True SOMENTE quando ScraperConfig.include_transcript=True (default False -- flag paga, cobrada por minuto de vídeo transcrito) + extra_run_input opcional.",
        "confiabilidade": "Confirmado via página do actor + input-schema (docs/research/..., §1.2) -- pay-per-event, ~$1.00/1.000 reels.",
        "notas": "Também suporta includeSharesCount (plano Starter+) e includeDownloadedVideo (cobrado por MB) -- nenhuma das duas está habilitada em ScraperConfig hoje (ver docs/research/..., §1.2, achado chave sobre sharesCount).",
    },
    {
        "papel": "Menções/UGC de terceiros (ugc_mentions) -- PILOTO, não produção",
        "actor_slug": "apify/instagram-tagged-scraper",
        "actor_id": "(resolvido pelo slug pela Apify -- não fixado como ID literal no código)",
        "dev": "Apify (oficial)",
        "status": "PILOTO -- schema definido e testado com dado sintético; piloto real grava só em data/pilot/*.json (scripts/run_apify_mentions_pilot.py), nunca na Bronze",
        "parametros_producao": "username=<usernames>, resultsLimit=<baixo no piloto> (ScraperConfig.mentions_actor_id, InstagramScraper.scrape_mentions).",
        "confiabilidade": "Escolhido sobre fetch_cat/instagram-mentions-scraper por reprodutibilidade (9.999 usuários, 5.0 estrelas vs. actor community \"under maintenance\", 2 usuários -- docs/research/..., §7.1). Schema de output confirmado por exemplo real da Apify, mas ainda NÃO confirmado 1:1 contra os 27 perfis do projeto.",
        "notas": "docs/research/apify-instagram-actors-cobra-mapping.md (§7) também mapeia uma rota alternativa sem integrar actor novo: reconfigurar o actor de perfis já em uso (shu8hvrXbJbY3Eb9W) para resultsType='mentions' -- capacidade confirmada, schema de output dessa rota específica NÃO confirmado por exemplo primário.",
    },
]

# ---------------------------------------------------------------------------
# 2. Descrições de coluna -- fallback técnico comum + overrides por tabela
# ---------------------------------------------------------------------------

COMMON_TECH: dict[str, str] = {
    "_ingested_at": "Timestamp UTC de quando o registro entrou na camada Bronze (BronzeWriter._add_ingestion_metadata).",
    "_run_id": "Identificador da execução do pipeline que gravou a linha (src/run_id.py) -- rastreia de qual chamada de pipeline.py/scripts/*.py a linha se origina.",
    "_source": "Origem do dado bruto -- sempre 'apify' hoje (src/data_extract/scraper.py).",
    "_source_layer": "Camada de origem da linha na Silver -- 'bronze' para a maioria, 'raw_xlsx' só para governors_metadata.",
    "_generated_at": "Timestamp UTC de quando a linha foi calculada/gravada na Gold -- distinto de _ingested_at (que é do dado bruto na Bronze).",
    "inputUrl": "URL do perfil de Instagram do governador (chave de junção mais usada entre perfis/posts/reels/Gold).",
    "ownerId": "Id do perfil (Bronze/Instagram) que publicou o post/reel.",
    "ownerUsername": "Username do perfil que publicou o post/reel/comentário.",
    "id": "Identificador único do registro na origem (Instagram/Apify) -- semântica varia por tabela, ver coluna Grão.",
    "username": "Nome de usuário do perfil de Instagram.",
    "shortCode": "Código curto do post/reel usado na URL pública do Instagram.",
    "timestamp": "Timestamp bruto do Apify, como string ISO -- ver `data_hora` para a versão já parseada/tipada (Silver).",
    "data_hora": "Timestamp parseado e convertido para America/Sao_Paulo (naive), a partir de `timestamp` bruto (PostCleaner._parse_timestamp).",
    "likesCount": "Número de curtidas.",
    "commentsCount": "Número de comentários.",
    "videoPlayCount": "Número de plays do vídeo (Reels/vídeo de feed).",
    "videoViewCount": "Número de views do vídeo (métrica bruta do Apify, distinta de videoPlayCount).",
    "videoDuration": "Duração do vídeo em segundos.",
    "caption": "Legenda/texto do post ou reel.",
    "fullName": "Nome completo exibido no perfil.",
    "followersCount": "Número de seguidores do perfil.",
    "followsCount": "Número de perfis que este perfil segue.",
    "postsCount": "Número total de posts do perfil (contagem exposta pelo Instagram, não contagem local coletada).",
    "verified": "Selo de verificação do Instagram.",
    "private": "Se o perfil é privado.",
    "isBusinessAccount": "Se o perfil está configurado como conta comercial.",
    "businessCategoryName": "Categoria de negócio declarada pelo perfil (quando conta comercial).",
    "type": "Tipo bruto do post retornado pelo Apify (Image/Video/Sidecar/Reel).",
    "Topic": "Id numérico do tópico BERTopic (-1 = ruído/sem tópico atribuído).",
    "Name": "Rótulo textual do tópico BERTopic -- determinístico (KeyBERTInspired) por padrão, ou refinado manualmente via Gemini (scripts/refine_topics.py).",
    "fonte": "Granularidade da linha dentro da tabela: 'comentario', 'legenda' ou 'transcricao' -- ver ADR 0020 Ficha 3 / issue #88.",
    "sentiment_label": "Rótulo de sentimento previsto: positive / neutral / negative (cardiffnlp/twitter-xlm-roberta-base-sentiment).",
    "sentiment_score": "Confiança do classificador na label prevista (NÃO 'o quão positivo/negativo') -- src/modeling/sentiment.py.",
    "cluster_label": "Rótulo do cluster atribuído pelo AutoClusterHPO (-1 = ruído do DBSCAN).",
    "cluster_algo": "Nome do algoritmo eleito pelo AutoClusterHPO para esta execução (KMeans/DBSCAN/Agglomerative).",
    "cluster_score": "Score CVI combinado (Silhouette + Calinski-Harabasz normalizado + Davies-Bouldin invertido) do algoritmo eleito -- ver src/modeling/clustering.py.",
    "content_type": "Discrimina se a linha é de 'reel' ou 'feed' dentro de governor_clusters (ADR 0020 Ficha 2 / issue #87).",
    "grupo": "Discrimina o grupo da regressão de performance-por-post: 'video' (Reels) ou 'estatico' (posts de imagem/carrossel).",
    "authorUsername": "Username de quem publicou o post de UGC (autor, distinto do governador mencionado) -- campo normalizado na Silver; na Bronze o actor real só preenche `ownerUsername` (ver override específico de ugc_mentions, coluna `ownerUsername` colide de nome com posts/reels/comentários).",
    "ownerFullName": "Nome completo de quem publicou o post de UGC (Bronze, confirmado pelo piloto real).",
    "paidPartnership": "Flag de parceria paga (publi) declarada pelo Instagram no post de UGC -- único campo de publi que o actor real expõe (piloto 2026-09-19); `isAd`/`isAffiliate` da especificação original não existem.",
    "is_organic": "Derivado de `paidPartnership`: True quando ausente/False -- separa apoio espontâneo de publi paga.",
    "governor_username": "Username do governador mencionado/marcado, resolvido cruzando `mentions` E `taggedUsers` (Bronze) com a lista de perfis conhecidos -- piloto real confirmou que ~69% dos posts só correlacionam via `taggedUsers`.",
    "mentions": "Lista de usernames @-mencionados em legenda/comentário do post de UGC, serializada como JSON string -- só ~31% dos posts reais têm este campo preenchido.",
    "taggedUsers": "Lista de objetos (um por pessoa marcada visualmente na foto/vídeo, com `username`/`full_name`/`is_verified`/`is_private`) do post de UGC, serializada como JSON string -- substitui o campo `matchTypes` (não existe no actor real); presente em ~69% dos posts, mais frequente que `mentions`.",
    "isSponsored": "Flag de conteúdo patrocinado no Reel (bruto do Apify).",
    "isCommentsDisabled": "Se os comentários estão desabilitados no post/reel.",
    "isPinned": "Se o reel está fixado no perfil.",
    "latestComments": "Lista bruta (JSON) dos comentários mais recentes do reel, retornada pelo Apify -- fonte de comments_clean.",
    "transcript": "Transcrição de fala do reel, via flag paga includeTranscript do actor -- nullable (vídeo mudo/flag desligada).",
    "hashtags": "Hashtags extraídas da legenda do post -- alimenta o BERTopic de tema sobre captions (ADR 0019 parte B).",
    "type_raw": "Campo bruto `type` do Apify (Image/Video/Sidecar), preservado antes de `Tipo` (FEED/REELS) ser atribuído -- preditor de Formato da regressão de performance-por-post.",
    "Tipo": "Granularidade fixada pelo cleaner: 'FEED' (posts_clean) ou 'REELS' (reels_clean) -- não confundir com `type_raw` (bruto do Apify).",
    "igtvVideoCount": "Número de vídeos IGTV do perfil (campo legado do Apify, baixo valor analítico hoje).",
    "hasChannel": "Se o perfil tem canal do Instagram habilitado.",
    "joinedRecently": "Flag do Apify indicando conta criada recentemente.",
    "locationName": "Nome do local marcado no post (quando presente).",
    "repliesCount": "Número de respostas a um comentário.",
    "id_reel": "Id do reel/post de origem do comentário/tópico -- chave de junção com reels_clean/posts_clean.",
    "id_comment": "Id único do comentário individual (pós-explosão de latestComments).",
    "text": "Texto avaliado -- comentário, legenda ou transcrição, dependendo da tabela/coluna `fonte`.",
    "comprimento texto": "Número de caracteres de `text` -- usado para filtrar comentários >= 512 caracteres (CommentCleaner.MAX_TEXT_LENGTH).",
    "Total de Engajamento": "likesCount + commentsCount deste reel (PostCleaner.clean_reels) -- por-REEL, insumo do PCA/AutoClusterHPO. Não confundir com 'TOTAL ENGAJAMENTO' (maiúsculo, com espaço) de governor_engagement, que é por-PERFIL agregado.",
    "nome": "Nome do governador (reference/governadores.xlsx, coluna 'Governador').",
    "uf": "Unidade Federativa do governador (reference/governadores.xlsx, coluna 'Unidade Federativa').",
    "partido": "Partido do governador (reference/governadores.xlsx, coluna 'Partido').",
}

TABLE_COLUMN_OVERRIDES: dict[str, dict[str, str]] = {
    "governor_engagement": {
        "commentsSum": "Soma de commentsCount de todos os posts+reels do perfil na execução (posts_clean + reels_clean concatenados).",
        "likesSum": "Soma de likesCount de todos os posts+reels do perfil na execução.",
        "count": "Número total de posts+reels do perfil considerados na agregação.",
        "minData": "Data do post/reel mais antigo do perfil considerado na agregação.",
        "maxData": "Data do post/reel mais recente do perfil considerado na agregação.",
        "TOTAL ENGAJAMENTO": "commentsSum + likesSum (engajamento bruto, sem peso).",
        "% ENGAJAMENTO": "(likesSum + commentsSum × _WC_COMENTARIO) / followersCount -- taxa de engajamento PONDERADA sobre a base de seguidores (0.0 quando followersCount <= 0).",
        "_WC_COMENTARIO": "Peso do comentário relativo à curtida nesta execução: total_likes / total_comments da base inteira (calibrado pelo próprio dado, não arbitrado) -- ADR 0018. Cai para 1.0 (peso igual) se não houver nenhum comentário na execução.",
        "RECENCIA": "1 / (dias_desde_o_post_mais_recente_da_BASE_INTEIRA - dias_desde_o_post_mais_recente_DESTE_perfil + 1) -- maior valor = perfil postou mais recentemente que a média da base. 0.0 para perfil sem nenhum post/reel (nunca 'recência máxima' por ausência de dado).",
        "FREQUENCIA": "count / (dias entre o post mais antigo e o mais recente do perfil, +1) -- posts por dia de atividade.",
    },
    "governor_engagement_history": {
        "commentsSum": "Ver governor_engagement -- mesmo cálculo, uma linha por execução em vez de snapshot único.",
        "likesSum": "Ver governor_engagement -- mesmo cálculo, uma linha por execução.",
        "count": "Ver governor_engagement -- mesmo cálculo, uma linha por execução.",
        "minData": "Ver governor_engagement -- mesmo cálculo, uma linha por execução.",
        "maxData": "Ver governor_engagement -- mesmo cálculo, uma linha por execução.",
        "TOTAL ENGAJAMENTO": "Ver governor_engagement -- mesmo cálculo, uma linha por execução (base para o CMGR de followersCount).",
        "% ENGAJAMENTO": "Ver governor_engagement -- mesmo cálculo, uma linha por execução.",
        "_WC_COMENTARIO": "Ver governor_engagement -- mesmo cálculo, recalibrado a cada execução (valor pode diferir entre linhas de execuções diferentes).",
        "RECENCIA": "Ver governor_engagement -- mesmo cálculo, uma linha por execução.",
        "FREQUENCIA": "Ver governor_engagement -- mesmo cálculo, uma linha por execução.",
    },
    "post_performance_coefficients": {
        "preditor": "Nome do preditor da regressão (varia por grupo -- ver coluna Notas da aba Tabelas).",
        "coeficiente": "Coeficiente estimado pelo LassoCV para este preditor (0.0 = preditor descartado pela regularização L1).",
        "r2_treino": "R² do modelo no conjunto de treino.",
        "r2_holdout": "R² do modelo no conjunto de holdout -- nulo só no caso degenerado de um grupo sem governador em holdout.",
        "n_treino": "Número de posts no conjunto de treino deste grupo.",
        "n_holdout": "Número de posts no conjunto de holdout deste grupo.",
        "alpha": "Hiperparâmetro de regularização (força da penalização L1) escolhido pelo LassoCV via validação cruzada.",
    },
    "post_performance_predictions": {
        "y_real": "Valor real de Y = (likesCount + commentsCount × _WC_COMENTARIO) / followersCount para este post.",
        "y_previsto": "Valor de Y previsto pela regressão Lasso treinada para o grupo (vídeo/estático) deste post.",
        "residuo": "y_real - y_previsto -- posts com resíduo muito positivo performaram acima do esperado pelo modelo, e vice-versa.",
    },
    "topic_priority_score": {
        "n_comentarios": "Número de comentários atribuídos a este tópico pelo BERTopic.",
        "alcance_topico": "Soma de (likesCount + repliesCount) dos comentários do tópico -- PROXY de visibilidade/ressonância, não alcance/views real.",
        "alcance_normalizado": "alcance_topico / (alcance_topico + 1) -- normalização que satura suavemente em [0,1), nunca divide por zero, e não depende de quais outros tópicos existem na mesma execução.",
        "proporcao_sentimento_positivo": "Fração de comentários do tópico com sentiment_label == 'positive'.",
        "confianca": "Média de sentiment_score (confiança do classificador, não polaridade) dos comentários do tópico.",
        "impacto": "alcance_normalizado × proporcao_sentimento_positivo.",
        "facilidade": "Fixa em 1.0 nesta v1 (FACILIDADE_V1) -- sem dado de custo de produção real para calibrar; o ranking de Score reduz-se, na prática, a Impacto × Confiança.",
        "score": "Impacto × Confiança × Facilidade -- ranking final de priorização de produção de conteúdo.",
    },
    "governor_nsm": {
        "n_comentarios_positivos": "Número de comentários (fonte == 'comentario') com sentiment_label == 'positive' deste perfil.",
        "n_comentarios_totais": "Número total de comentários (fonte == 'comentario') deste perfil.",
        "proporcao_positivos": "n_comentarios_positivos / n_comentarios_totais -- 0.0 quando o perfil não tem nenhum comentário (nunca NaN/erro).",
        "total_engajamento": "Cópia de governor_engagement['TOTAL ENGAJAMENTO'] para este perfil, mantida para auditoria/contraste no dashboard.",
        "count_posts": "Cópia de governor_engagement['count'] para este perfil.",
        "alcance_medio": "total_engajamento / count_posts -- PROXY de alcance (intensidade de engajamento por post), não alcance/views real. 0.0 quando count_posts == 0.",
        "nsm": "proporcao_positivos × alcance_medio -- North Star Metric de engajamento QUALIFICADO (pondera qualidade de reação, não só volume).",
    },
    "governor_growth_metrics": {
        "valor_inicial": "Valor da métrica-base (followersCount) no primeiro mês-calendário com execução registrada.",
        "valor_final": "Valor da métrica-base (followersCount) no último mês-calendário com execução registrada.",
        "cmgr": "(valor_final / valor_inicial) ** (1 / n_meses) - 1 -- crescimento mensal composto. NaN quando não calculável (ver cmgr_motivo).",
        "cmgr_n_periodos": "Número de meses-calendário com execução registrada usados no cálculo do CMGR.",
        "cmgr_confiavel": "False sempre que cmgr_n_periodos < 6 (MIN_PERIODS_CONFIAVEL) -- sinaliza resultado ilustrativo, não conclusivo.",
        "cmgr_motivo": "Motivo do CMGR ser NaN, quando aplicável: historico_insuficiente / periodo_zero / valor_inicial_invalido.",
        "retencao": "Média de valor_t/valor_(t-1) (capada em 1.0) do share mensal de sentimento positivo entre meses consecutivos -- 1.0 = manteve 100% (ou mais); mede o quanto do período anterior foi retido, não crescimento.",
        "retencao_n_periodos": "Número de meses-calendário com execução registrada usados no cálculo da retenção.",
        "retencao_n_pares_validos": "Número de pares de meses consecutivos válidos usados na média da retenção.",
        "retencao_confiavel": "False sempre que retencao_n_periodos < 6 (MIN_PERIODS_CONFIAVEL).",
        "retencao_motivo": "Motivo da retenção ser NaN, quando aplicável (mesmas categorias do cmgr_motivo).",
        "ilustrativo": "True enquanto o pipeline não tiver acumulado histórico real suficiente -- sinaliza que o valor valida a FÓRMULA, não sustenta conclusão definitiva no TCC.",
        "nota": "Texto explicando por que o resultado é (ou não) ilustrativo, para exibição direta em dashboard/relatório sem reprocessar nada.",
    },
    "ugc_mentions (schema definido, ainda não materializado)": {
        # `ownerUsername`/`ownerId` aqui são do AUTOR TERCEIRO do UGC (quem
        # marcou/mencionou o governador), não do próprio governador --
        # diferente do significado genérico em COMMON_TECH (posts/reels,
        # onde owner* É o governador). Override específico para não
        # confundir os dois (F601: eram chaves duplicadas em COMMON_TECH
        # até 2026-09-19, a segunda sobrescrevia a primeira silenciosamente).
        "ownerUsername": "Username de quem publicou o post de UGC (autor terceiro que marcou/mencionou o governador -- Bronze, nome real do actor apify/instagram-tagged-scraper). Normalizado para `authorUsername` na Silver.",
        "ownerId": "Id do perfil de quem publicou o post de UGC (autor terceiro, Bronze, confirmado pelo piloto real) -- distinto do `ownerId` de posts/reels, que é o próprio governador.",
    },
    "governor_ugc_mentions (schema definido, ainda não materializado)": {
        "caption": "Legenda do post de UGC (do autor terceiro, não do governador).",
    },
    "post_performance_coefficients_NA": {},
}

# ---------------------------------------------------------------------------
# 3. Linhagem (fluxo entre camadas)
# ---------------------------------------------------------------------------

LINEAGE: list[dict] = [
    {
        "origem": "Apify (apify/instagram-scraper, ID shu8hvrXbJbY3Eb9W, modo resultsType='details' -- ver aba Actors Apify)",
        "destino": "Landing zone: data/landing/<run_id>/profiles.json (local) ou /tmp/landing/<run_id>/profiles.json (Lambda, efêmero)",
        "transformacao": "Arquivamento do JSON bruto retornado pela Apify, SEM projeção de schema -- fidelidade total, inclusive de campos que a Bronze descarta silenciosamente. Sempre executado antes da escrita Bronze, para que uma falha nesta não implique perda do dado já raspado (e já pago).",
        "modulo": "src/data_extract/ingestion.py (archive_raw_json / extract_and_land)",
    },
    {
        "origem": "Landing zone: profiles.json",
        "destino": "Bronze: instagram_profiles",
        "transformacao": "Ingestão bruta + metadados de execução (_ingested_at/_run_id/_source); serialização de campos list/dict para JSON string. Destino físico: data/bronze/instagram_profiles (local) ou s3://<bucket>/bronze/instagram_profiles (Lambda, quando infra AWS aplicada).",
        "modulo": "src/data_extract/bronze_writer.py",
    },
    {
        "origem": "Apify (apify/instagram-post-scraper -- ver aba Actors Apify)",
        "destino": "Landing zone: data/landing/<run_id>/posts.json (local) ou /tmp/landing/<run_id>/posts.json (Lambda, efêmero)",
        "transformacao": "Idem profiles.json.",
        "modulo": "src/data_extract/ingestion.py (archive_raw_json / extract_and_land)",
    },
    {
        "origem": "Landing zone: posts.json",
        "destino": "Bronze: instagram_posts",
        "transformacao": "Idem instagram_profiles. Destino físico: data/bronze/instagram_posts (local) ou s3://<bucket>/bronze/instagram_posts (Lambda).",
        "modulo": "src/data_extract/bronze_writer.py",
    },
    {
        "origem": "Apify (apify/instagram-reel-scraper -- ver aba Actors Apify)",
        "destino": "Landing zone: data/landing/<run_id>/reels.json (local) ou /tmp/landing/<run_id>/reels.json (Lambda, efêmero)",
        "transformacao": "Idem profiles.json; payload já inclui latestComments e, opcionalmente, transcript (flag paga includeTranscript).",
        "modulo": "src/data_extract/ingestion.py (archive_raw_json / extract_and_land)",
    },
    {
        "origem": "Landing zone: reels.json",
        "destino": "Bronze: instagram_reels",
        "transformacao": "Idem instagram_profiles; inclui latestComments e, opcionalmente, transcript (flag paga includeTranscript). Destino físico: data/bronze/instagram_reels (local) ou s3://<bucket>/bronze/instagram_reels (Lambda).",
        "modulo": "src/data_extract/bronze_writer.py",
    },
    {
        "origem": "Bronze: instagram_profiles",
        "destino": "Silver: profiles_clean",
        "transformacao": "Descarta linha sem id; drop de colunas de baixo valor (biografia, URLs de foto); cast para int32/bool não-nulo; deduplicação por id; fallback de fullName.",
        "modulo": "src/features/silver/profile_cleaner.py",
    },
    {
        "origem": "Bronze: instagram_posts",
        "destino": "Silver: posts_clean",
        "transformacao": "Descarta linha sem id; parse de timestamp -> data_hora (America/Sao_Paulo); preserva type_raw; fixa Tipo='FEED'; cast numérico; drop de colunas ruído (mentions/images/musicInfo/...); deduplicação por id.",
        "modulo": "src/features/silver/post_cleaner.py",
    },
    {
        "origem": "Bronze: instagram_reels",
        "destino": "Silver: reels_clean",
        "transformacao": "Mesma limpeza de posts_clean, mais: fixa Tipo='REELS'; calcula 'Total de Engajamento' (likes+comentários); propaga transcript sem alteração.",
        "modulo": "src/features/silver/post_cleaner.py",
    },
    {
        "origem": "Bronze: instagram_reels (campo latestComments)",
        "destino": "Silver: comments_clean",
        "transformacao": "Explode a lista JSON de comentários em uma linha por comentário; filtra texto >= 512 caracteres; deduplicação por id_comment.",
        "modulo": "src/features/silver/comment_cleaner.py",
    },
    {
        "origem": "reference/governadores.xlsx",
        "destino": "Silver: governors_metadata",
        "transformacao": "Renomeia colunas (Governador->nome, Unidade Federativa->uf, Partido->partido, Link->inputUrl); dedup por inputUrl.",
        "modulo": "src/features/silver/governors_metadata_cleaner.py",
    },
    {
        "origem": "Silver: profiles_clean + posts_clean + reels_clean",
        "destino": "Gold: governor_engagement / governor_engagement_history",
        "transformacao": "Agrega posts+reels por perfil; calcula TOTAL ENGAJAMENTO, % ENGAJAMENTO (ponderado por _WC_COMENTARIO), RECENCIA e FREQUENCIA.",
        "modulo": "src/features/gold/engagement_aggregator.py",
    },
    {
        "origem": "Silver: comments_clean + reels_clean/posts_clean (legenda/transcrição)",
        "destino": "Gold: governor_sentiment / governor_sentiment_history",
        "transformacao": "Classificação de sentimento (cardiffnlp/twitter-xlm-roberta-base-sentiment) + tópico BERTopic determinístico, por comentário/legenda/transcrição.",
        "modulo": "src/modeling/sentiment.py + src/modeling/topics.py, gravado por src/features/gold/model_enricher.py",
    },
    {
        "origem": "Gold: governor_sentiment",
        "destino": "governor_sentiment (rótulos atualizados)",
        "transformacao": "Refinamento manual dos rótulos de tópico (Name) via Gemini -- reescreve a mesma tabela, não gera nova medição de sentimento.",
        "modulo": "scripts/refine_topics.py + src/modeling/gemini_refiner.py",
    },
    {
        "origem": "Silver: reels_clean + posts_clean",
        "destino": "Gold: governor_clusters",
        "transformacao": "PCA (engajamento/duração) + AutoClusterHPO (KMeans/DBSCAN/Agglomerative eleito por score CVI) por post; content_type discrimina reel/feed.",
        "modulo": "src/modeling/clustering.py, gravado por src/features/gold/model_enricher.py",
    },
    {
        "origem": "Gold: governor_engagement",
        "destino": "Gold: governor_profile_clusters_engagement",
        "transformacao": "Mesma pipeline PCA->AutoClusterHPO, mas com features agregadas por PERFIL em vez de por post.",
        "modulo": "src/modeling/profile_clustering.py, via src/modeling/orchestration.py::run_deterministic_modeling (ou isoladamente via scripts/run_profile_clustering_engagement.py)",
    },
    {
        "origem": "Silver: posts_clean (caption/hashtags/Topic) + reels_clean + Gold: governor_engagement",
        "destino": "Gold: post_performance_coefficients / post_performance_predictions",
        "transformacao": "Regressão Lasso de Y = (likes+comentários×Wc)/seguidores sobre preditores temporais/de formato/conteúdo, separada em grupo vídeo/estático; checagem de circularidade antes de treinar.",
        "modulo": "src/modeling/post_performance.py",
    },
    {
        "origem": "Gold: governor_sentiment (fonte='comentario')",
        "destino": "Gold: topic_priority_score",
        "transformacao": "Score ICE = Impacto(alcance_normalizado×%positivo) × Confiança(sentiment_score médio) × Facilidade(fixa=1.0), agregado por Topic.",
        "modulo": "src/features/gold/topic_priority_scorer.py",
    },
    {
        "origem": "Gold: governor_sentiment (fonte='comentario') + governor_engagement",
        "destino": "Gold: governor_nsm",
        "transformacao": "NSM = (%comentários positivos) × (TOTAL ENGAJAMENTO / count, como proxy de alcance), merge outer por inputUrl.",
        "modulo": "src/features/gold/nsm_scorer.py",
    },
    {
        "origem": "Gold: governor_engagement_history + governor_sentiment_history",
        "destino": "Gold: governor_growth_metrics",
        "transformacao": "CMGR sobre followersCount mensal + retenção sobre share mensal de sentimento positivo; marca ilustrativo/confiavel conforme volume de histórico.",
        "modulo": "src/modeling/growth_history.py + scripts/run_growth_metrics.py",
    },
    {
        "origem": "Apify (apify/instagram-tagged-scraper -- ver aba Actors Apify)",
        "destino": "Bronze/Silver/Gold: ugc_mentions / governor_ugc_mentions",
        "transformacao": "Coleta -> landing zone -> Bronze -> Silver (dedup id/shortCode, normalização de handle, resolução de governor_username via mentions+taggedUsers) -> Gold (is_organic a partir de paidPartnership), tudo sob o mesmo run_id -- mesmo padrão de scripts/run_apify_backfill.py. Schema corrigido contra o piloto real (scripts/run_apify_mentions_pilot.py, 2026-09-19, data/pilot/*.json, fora do Delta Lake). Writer de produção implementado e testado, mas ainda NUNCA disparado contra a Apify de produção (custo real).",
        "modulo": "scripts/run_ugc_mentions.py + src/data_extract/bronze_writer.py + src/features/silver/ugc_mention_cleaner.py + src/features/gold/ugc_mentions_aggregator.py",
    },
    {
        "origem": "Gold (todas as tabelas acima)",
        "destino": "Dashboard Streamlit (dashboard/app.py + dashboard/screens/*.py, ADR 0021; pages/02-03 remanescentes, órfãs) e notebooks/03-07",
        "transformacao": "Leitura read-only via src/repositories/delta_repository.py (DeltaRepository) -- nunca escreve, save() levanta NotImplementedError deliberadamente.",
        "modulo": "src/repositories/delta_repository.py + dashboard/core/* + src/dashboard/*",
    },
]

# ---------------------------------------------------------------------------
# 4. Glossário de métricas derivadas
# ---------------------------------------------------------------------------

GLOSSARY: list[dict] = [
    {
        "metrica": "% ENGAJAMENTO",
        "tabela": "governor_engagement / governor_engagement_history",
        "formula": "(likesSum + commentsSum × _WC_COMENTARIO) / followersCount",
        "interpretacao": "Taxa de engajamento por perfil, ponderando comentário mais que curtida (peso calibrado pela própria base).",
        "limitacoes": "0.0 quando followersCount <= 0. _WC_COMENTARIO é recalculado a cada execução (varia entre execuções, não é uma constante fixa do projeto).",
    },
    {
        "metrica": "_WC_COMENTARIO",
        "tabela": "governor_engagement / governor_engagement_history",
        "formula": "total_likes_da_execução / total_comentários_da_execução (1.0 se total_comentários == 0)",
        "interpretacao": "Peso relativo do comentário vs. curtida -- ADR 0018: comentário custa mais atenção do que curtida.",
        "limitacoes": "É um valor ÚNICO por execução (mesmo peso para todos os perfis daquela execução), não por perfil.",
    },
    {
        "metrica": "RECENCIA",
        "tabela": "governor_engagement / governor_engagement_history",
        "formula": "1 / (dias_desde_o_post_mais_recente_da_base - dias_desde_o_post_mais_recente_do_perfil + 1)",
        "interpretacao": "Quão perto este perfil está de ser o mais recentemente ativo da base inteira.",
        "limitacoes": "0.0 (não recência máxima) para perfil sem nenhum post/reel -- tratamento explícito para não inflar ausência de dado.",
    },
    {
        "metrica": "FREQUENCIA",
        "tabela": "governor_engagement / governor_engagement_history",
        "formula": "count / (dias_entre_primeiro_e_último_post_do_perfil + 1)",
        "interpretacao": "Posts por dia de atividade do perfil.",
        "limitacoes": "Não distingue pausas longas de atividade constante em baixo volume -- é uma média sobre toda a janela coletada.",
    },
    {
        "metrica": "Score ICE (topic_priority_score.score)",
        "tabela": "topic_priority_score",
        "formula": "Impacto × Confiança × Facilidade, onde Impacto = alcance_normalizado × %positivo, alcance_normalizado = alcance_topico/(alcance_topico+1)",
        "interpretacao": "Ranking de priorização de tópicos de comentário para produção de conteúdo -- ADR 0020 Ficha 6.",
        "limitacoes": "Facilidade fixa em 1.0 (v1, sem dado de custo real); alcance_topico é proxy (likes+replies do comentário), não views/alcance real.",
    },
    {
        "metrica": "NSM (governor_nsm.nsm)",
        "tabela": "governor_nsm",
        "formula": "(comentários positivos / comentários totais) × alcance_medio, alcance_medio = TOTAL ENGAJAMENTO / count",
        "interpretacao": "North Star Metric de engajamento QUALIFICADO por perfil -- ADR 0020 Ficha 5.",
        "limitacoes": "alcance_medio é proxy de intensidade de engajamento por post, não alcance/views real. Validado contra os 27 perfis reais em 2026-09-19: 25/27 perfis mudam de posição vs. ranking por engajamento bruto (ver aba Tabelas / ADR 0020 Ficha 5).",
    },
    {
        "metrica": "CMGR (governor_growth_metrics.cmgr)",
        "tabela": "governor_growth_metrics",
        "formula": "(valor_final / valor_inicial) ** (1 / n_meses) - 1, sobre followersCount mensal",
        "interpretacao": "Crescimento mensal composto de seguidores -- ADR 0020 Ficha 7.",
        "limitacoes": "cmgr_confiavel=False com menos de 6 execuções mensais acumuladas -- resultado atual (2026-09) é ILUSTRATIVO, valida a fórmula, não sustenta conclusão real no TCC.",
    },
    {
        "metrica": "Retenção (governor_growth_metrics.retencao)",
        "tabela": "governor_growth_metrics",
        "formula": "Média (capada em 1.0) de valor_t/valor_(t-1) do share mensal de sentimento positivo entre meses consecutivos",
        "interpretacao": "Quanto do sentimento positivo do mês anterior foi mantido -- mede retenção, não crescimento (CMGR cobre magnitude).",
        "limitacoes": "Mesma ressalva de confiabilidade do CMGR (min. 6 períodos).",
    },
    {
        "metrica": "Y da regressão de performance-por-post",
        "tabela": "post_performance_predictions (y_real/y_previsto/residuo)",
        "formula": "(likesCount + commentsCount × _WC_COMENTARIO) / followersCount, por POST (não por perfil)",
        "interpretacao": "Mesma lógica ponderada de % ENGAJAMENTO, mas na granularidade de post individual -- variável explicada pela regressão Lasso (ADR 0019 parte C).",
        "limitacoes": "Preditores derivados das mesmas colunas brutas de Y são bloqueados por checagem de circularidade (CircularityError) antes do treino.",
    },
    {
        "metrica": "cluster_score (governor_clusters / governor_profile_clusters_engagement)",
        "tabela": "governor_clusters / governor_profile_clusters_engagement",
        "formula": "Silhouette + Calinski-Harabasz normalizado (tanh(chi/10000)) + Davies-Bouldin invertido (tanh(1/dbi)), combinado",
        "interpretacao": "Score CVI (Cluster Validity Index) combinado usado pelo AutoClusterHPO para eleger o algoritmo/hiperparâmetros de clusterização.",
        "limitacoes": "Pontos de ruído do DBSCAN (cluster_label=-1) são filtrados ANTES do cálculo do CVI, para não distorcer a comparação entre algoritmos.",
    },
]

# ---------------------------------------------------------------------------
# 5. Construção da planilha
# ---------------------------------------------------------------------------

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF")
WRAP = Alignment(wrap_text=True, vertical="top")
TITLE_FONT = Font(bold=True, size=14)


def _pa_type_to_str(t: pa.DataType) -> str:
    if pa.types.is_timestamp(t):
        tz = f", tz={t.tz}" if t.tz else ""
        return f"timestamp[{t.unit}{tz}]"
    return str(t)


def _style_header(ws: Worksheet, n_cols: int) -> None:
    for col in range(1, n_cols + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def _set_widths(ws: Worksheet, widths: list[int]) -> None:
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _write_rows(ws: Worksheet, header: list[str], rows: list[list], widths: list[int]) -> None:
    ws.append(header)
    for row in rows:
        ws.append(row)
        r = ws.max_row
        for c in range(1, len(header) + 1):
            ws.cell(row=r, column=c).alignment = WRAP
    _set_widths(ws, widths)
    _style_header(ws, len(header))


def build_overview_sheet(wb: Workbook) -> None:
    ws = wb.active
    ws.title = "Visão Geral"
    ws.column_dimensions["A"].width = 100
    lines = [
        ("Dicionário de Dados -- Arquitetura Medallion", TITLE_FONT),
        ("Técnicas de NLP em Dados do Instagram -- TCC, Ciência de Dados e IA, IESB", Font(italic=True)),
        ("", None),
        ("Fonte técnica: src/schemas_delta.py (contratos PyArrow validados em runtime pelos writers). "
         "Fonte de negócio: leitura direta dos módulos src/features/*, src/modeling/*, config/settings.py. "
         "Fonte de actors/parâmetros de extração: src/data_extract/scraper.py e src/data_extract/ingestion.py "
         "(código realmente em produção), cruzada com a pesquisa primária em "
         "docs/research/apify-instagram-actors-cobra-mapping.md (preço/adoção/schema, consultada na Apify Store "
         "e API pública em 2026-09-08).", None),
        ("Gerado por: scripts/generate_data_dictionary.py -- reexecutar após qualquer mudança de schema.", None),
        ("", None),
        ("Camadas", Font(bold=True, size=12)),
        ("Bronze -- append-only, fidelidade total ao retorno bruto do Apify (data/bronze/).", None),
        ("Silver -- limpo e conformado a um contrato de tipos fechado; overwrite por execução (data/silver/).", None),
        ("Gold -- agregados e resultados de modelagem, prontos para consumo por dashboard/TCC (data/gold/).", None),
        ("", None),
        ("Legenda de Status (aba Tabelas)", Font(bold=True, size=12)),
        ("Produção -- escrita e lida por pelo menos um caminho de código de produção, com dado real esperado em data/.", None),
        ("Produção (ressalva) -- em produção, mas com uma limitação declarada explicitamente pelo próprio código-fonte "
         "(ex.: histórico curto demais para ser conclusivo) -- ver coluna Notas.", None),
        ("PILOTO -- contrato de schema definido e cobertura de teste com dado sintético, mas SEM caminho de escrita de "
         "produção ainda; nenhuma linha real esperada em data/ hoje (ADR 0020 Ficha 8 / issue #93, UGC de menções).", None),
        ("", None),
        ("Contagem de tabelas", Font(bold=True, size=12)),
        ("Bronze: 4  |  Silver: 6  |  Gold: 13  |  Total: 23", None),
        ("", None),
        ("Como navegar", Font(bold=True, size=12)),
        ("1. Aba 'Tabelas' -- visão de 1 linha por tabela (grão, escrita, leitura, status, ADR).", None),
        ("2. Abas 'Colunas - Bronze/Silver/Gold' -- 1 linha por coluna de cada tabela da camada.", None),
        ("3. Aba 'Linhagem' -- de onde cada tabela vem e o que a transformação aplica, incluindo o hop pela "
         "landing zone (data/landing/<run_id>/*.json) ANTES de qualquer escrita Bronze.", None),
        ("4. Aba 'Actors Apify' -- qual actor (slug + ID técnico) raspa cada entidade Bronze, com quais "
         "parâmetros REALMENTE usados em produção (src/data_extract/scraper.py), status produção/piloto e "
         "confiabilidade da fonte (cruzado com docs/research/apify-instagram-actors-cobra-mapping.md).", None),
        ("5. Aba 'Glossário de Métricas' -- fórmula completa de cada métrica derivada (% ENGAJAMENTO, NSM, Score ICE, "
         "CMGR, retenção, Y da regressão, cluster_score).", None),
    ]
    for text, font in lines:
        ws.append([text])
        if font:
            ws.cell(row=ws.max_row, column=1).font = font
        ws.cell(row=ws.max_row, column=1).alignment = Alignment(wrap_text=True, vertical="top")


def build_tables_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Tabelas")
    header = [
        "Camada", "Tabela", "Caminho", "Grão (o que é 1 linha)", "Modo de escrita",
        "Escrito por", "Lido por", "Status", "ADR / Issue", "Descrição de negócio", "Notas / Limitações",
    ]
    rows = [
        [
            t["camada"], t["tabela"], t["caminho"], t["grao"], t["modo_escrita"],
            t["escrito_por"], t["lido_por"], t["status"], t["adr"], t["descricao"], t["notas"],
        ]
        for t in TABLES
    ]
    widths = [9, 32, 34, 42, 14, 40, 40, 30, 26, 46, 55]
    _write_rows(ws, header, rows, widths)


def build_columns_sheet(wb: Workbook, camada: str) -> None:
    ws = wb.create_sheet(f"Colunas - {camada}")
    header = ["Tabela", "Coluna", "Tipo", "Nullable", "Descrição de negócio / origem"]
    rows = []
    for t in TABLES:
        if t["camada"] != camada:
            continue
        schema: pa.Schema = t["schema"]
        overrides = TABLE_COLUMN_OVERRIDES.get(t["tabela"], {})
        for field in schema:
            desc = overrides.get(field.name) or COMMON_TECH.get(field.name) or MISSING_DESC
            rows.append(
                [
                    t["tabela"],
                    field.name,
                    _pa_type_to_str(field.type),
                    "Sim" if field.nullable else "Não",
                    desc,
                ]
            )
    widths = [36, 26, 22, 10, 90]
    _write_rows(ws, header, rows, widths)


def build_lineage_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Linhagem")
    header = ["Origem", "Destino", "Transformação aplicada", "Módulo responsável"]
    rows = [[link["origem"], link["destino"], link["transformacao"], link["modulo"]] for link in LINEAGE]
    widths = [40, 40, 70, 46]
    _write_rows(ws, header, rows, widths)


def build_actors_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Actors Apify")
    header = [
        "Papel no pipeline", "Actor (slug)", "Actor ID técnico", "Desenvolvedor",
        "Status", "Parâmetros usados em produção", "Confiabilidade da fonte", "Notas",
    ]
    rows = [
        [
            a["papel"], a["actor_slug"], a["actor_id"], a["dev"], a["status"],
            a["parametros_producao"], a["confiabilidade"], a["notas"],
        ]
        for a in APIFY_ACTORS
    ]
    widths = [34, 30, 30, 16, 20, 55, 50, 55]
    _write_rows(ws, header, rows, widths)


def build_glossary_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Glossário de Métricas")
    header = ["Métrica", "Tabela", "Fórmula", "Interpretação", "Limitações conhecidas"]
    rows = [
        [g["metrica"], g["tabela"], g["formula"], g["interpretacao"], g["limitacoes"]]
        for g in GLOSSARY
    ]
    widths = [26, 36, 46, 46, 55]
    _write_rows(ws, header, rows, widths)


def main() -> None:
    wb = Workbook()
    build_overview_sheet(wb)
    build_tables_sheet(wb)
    for camada in ("Bronze", "Silver", "Gold"):
        build_columns_sheet(wb, camada)
    build_lineage_sheet(wb)
    build_actors_sheet(wb)
    build_glossary_sheet(wb)

    # Sanidade: qualquer coluna sem descrição fica visível na planilha (não
    # falha a geração), mas também é reportada no terminal para revisão.
    missing = []
    for t in TABLES:
        overrides = TABLE_COLUMN_OVERRIDES.get(t["tabela"], {})
        for field in t["schema"]:
            if field.name not in overrides and field.name not in COMMON_TECH:
                missing.append(f"{t['tabela']}.{field.name}")
    if missing:
        print(f"[AVISO] {len(missing)} coluna(s) sem descrição -- revisar COMMON_TECH/TABLE_COLUMN_OVERRIDES:")
        for m in missing:
            print(f"  - {m}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUTPUT_PATH)
    n_cols = sum(len(t["schema"]) for t in TABLES)
    print(f"OK -- {len(TABLES)} tabelas, {n_cols} colunas documentadas em {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
