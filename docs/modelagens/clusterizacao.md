# Clusterização de perfis e de conteúdo (reels e posts de feed)

**Status:** a documentar
**Atualizada em:** 2026-10-11

> Justificativa do status: o método está em uso e o dashboard o apresenta sob o selo "agrupamento experimental"
> (`CONTEXT.md`, verbete "Grupo de desempenho"), mas nenhuma fonte registra validação do resultado além do diagnóstico de
> tabela (tamanho dos clusters, completude). Não há pergunta aberta formalizada nem notebook comparando métodos, então
> `em avaliação` também não se aplica.
>
> Escopo: o catálogo chama esta modelagem de "perfis e comentários". No código, a clusterização existe para **perfis de
> governador** e para **conteúdo** (reels e posts de feed). Agrupar comentários é feito pelo modelo de tópicos, descrito em
> [topicos.md](topicos.md) ("Grupo de comentários", `CONTEXT.md`); não há clusterização de comentários separada.

## Pergunta de negócio

- **Perfis:** quais governadores têm um padrão de engajamento parecido (engajamento, recência, frequência de postagem)?
- **Conteúdo:** que tipos de reel e de post de feed existem, em termos de engajamento e duração, e quais se destacam
  ("Grupo de desempenho", `CONTEXT.md`)? O analista de assessoria os vê como "Cluster 1", "Cluster 2"… numerados por
  tamanho, na análise de reels de "Comparar perfis", sempre sob o selo "agrupamento experimental" (`CONTEXT.md`).

## Dados e série

| Clusterização | Entrada | Granularidade | Tabela Gold |
|---|---|---|---|
| Reels | `reels_clean` (Silver): `commentsCount`, `likesCount`, `videoPlayCount`, `videoDuration` | 1 linha por reel | `governor_clusters_reels` |
| Posts de feed | `posts_clean` (Silver): `commentsCount`, `likesCount` | 1 linha por post | `governor_clusters_posts` |
| Perfis | `governor_engagement` (Gold): `% ENGAJAMENTO`, `RECENCIA`, `FREQUENCIA` | 1 linha por governador | `governor_profile_clusters_engagement` |

Fontes: `PCAConfig`, `FeedPCAConfig` e `ModelingConfig.profile_cluster` em `src/modeling/config.py`.

- Posts de feed não têm `videoPlayCount` nem `videoDuration`; por isso as cargas do PCA de feed são diferentes das do PCA de
  reel, o que é esperado (docstring de `FeedPCAConfig`).
- Desde a issue #152, reels e posts de feed vivem em duas tabelas Gold separadas (antes era `governor_clusters` com a coluna
  `content_type`): `posts_clean` e `reels_clean` se sobrepõem, porque um reel também é capturado pelo scraper de posts, e a
  tabela combinada duplicava o mesmo post (`notebooks/diagnostico_medallion/gold_clusters.ipynb`, célula de abertura; comentário
  em `src/modeling/orchestration.py`).
- `followersCount` não entra na clusterização de perfis (ADR 0018, Contexto).
- Tamanho da amostra de perfis: o diagnóstico salvo de `governor_profile_clusters_engagement` tem 27 linhas
  (16 + 8 + 3, ver "Validação"). O universo de governadores no dado posterior é 26, porque a Silver filtra governadores
  removidos de `governadores.xlsx` (ADR 0030, "Como ficou implementado").
- Tamanho das amostras de reels e posts: não registrado nas fontes consultadas (as células do notebook
  `gold_clusters.ipynb` não têm saída salva).

## Método escolhido

1. **Reels e feed:** PCA (`reduce_dimensions`, `src/modeling/pca.py`) sobre as colunas padronizadas (`StandardScaler`), com 2
   componentes, gravados nas colunas fixas `PC1_Engajamento_videoPlay` e `PC2_videoDuration`; depois `AutoClusterHPO` sobre
   essas duas componentes (`ClusterConfig`).
2. **Perfis:** `AutoClusterHPO` direto sobre `% ENGAJAMENTO`, `RECENCIA` e `FREQUENCIA`, com `max_n_clusters=6` para não deixar
   o espaço de busca folgado demais para a amostra pequena (`ModelingConfig.profile_cluster`).
3. **`AutoClusterHPO`** (`src/modeling/clustering.py`): padroniza as features e busca hiperparâmetros com Hyperopt (TPE,
   `max_evals_per_algo=100`, `random_state=42`) para três algoritmos, escolhendo o melhor pontuado:
   - `KMeans`, com `n_clusters` a partir de 3;
   - `DBSCAN`, com `eps` entre 0,1 e 2,0 e `min_samples` entre 2 e 20;
   - `AgglomerativeClustering`, com `n_clusters` a partir de 3 e `linkage` entre `ward`, `complete`, `average` e `single`.
   A pontuação é a média de três índices de validação interna: silhouette, `tanh(Calinski-Harabasz / 10000)` e
   `tanh(1 / Davies-Bouldin)`. Pontos de ruído do DBSCAN (`-1`) saem do cálculo dos índices. Sem `max_n_clusters`, o teto é
   `min(21, int(n_amostras * 0.5) + 1)`, nunca menor que 3.
4. **Rótulo de ruído:** `cluster_label == -1` (ruído do DBSCAN) aparece no produto como "casos atípicos / virais", nunca como
   "-1" (`CONTEXT.md`, "Grupo de desempenho").
5. **Execução:** estágio de `run_deterministic_modeling` (`src/modeling/orchestration.py`); a clusterização de perfis também
   roda isolada em `scripts/run_profile_clustering_engagement.py`. Falha na clusterização de perfis não derruba os demais
   estágios (bloco `try/except` na orquestração).

## Alternativas avaliadas

Só constam as alternativas registradas nos ADRs e no código.

| Alternativa | Vantagem | Desvantagem | Resultado |
|---|---|---|---|
| Algoritmos KMeans, DBSCAN e Aglomerativo, escolhidos por busca de hiperparâmetros e índice combinado | O algoritmo e o número de clusters emergem dos dados | O índice combinado é uma escolha do projeto; nenhuma fonte o compara a outro critério | Em uso (`AutoClusterHPO`) |
| Tabela única `governor_clusters` com `content_type` (ADR 0020, Ficha 2), em vez de `governor_feed_clusters` separada | Uma consulta com filtro, sem unir duas tabelas (justificativa da ADR 0020) | Duplicava o mesmo post real sob os dois `content_type` | Substituída por duas tabelas, uma por formato (`governor_clusters_reels`, `governor_clusters_posts`), issue #152 |
| Estender os clusters de perfil com `followersCount` para mapear aos quadrantes da VHL (ADR 0018) | Reuso | Força correspondência entre cluster livre e quatro categorias fixas | Rejeitada; a matriz de quadrantes é uma feature independente |
| Outras técnicas de clusterização (HDBSCAN, GMM, etc.) | — | — | Não registrado |

## Validação

O que está registrado:

- **Diagnóstico salvo de perfis** (`notebooks/diagnostico_medallion/gold_profile_clusters_engagement.ipynb`): 27 perfis, sem
  duplicata por `inputUrl`, sem nulos. Distribuição de `cluster_label`: `-1` com 16 perfis, `0` com 8 e `1` com 3. Algoritmo
  vencedor `DBSCAN`, `cluster_score` 0,6038 (valor lido nas linhas de ruído exibidas no notebook). Ou seja, 16 de 27 perfis
  (cerca de 59%) ficaram como ruído, o que é um limite relevante para a leitura do agrupamento de perfis.
- **Reels e feed** (`gold_clusters.ipynb`): o notebook roda as seções de completude, distribuição, covariáveis e outliers, mas
  as células não têm saída salva; nenhum número de reels ou feed está registrado.
- **PCA** (`notebooks/03_modelagem_hibrida.ipynb`): o notebook calcula variância explicada e cargas, mas sem saída salva; os
  valores não estão registrados.
- Teste automatizado do código: `tests/test_clustering.py`, `tests/test_profile_clustering.py`, `tests/test_pca.py`.
- Não há validação externa dos clusters (por exemplo, revisão manual do significado de cada grupo) registrada. O nome e a
  descrição curados de cada cluster no dashboard ficam sob o selo "agrupamento experimental" (`CONTEXT.md`).

## Limitações

- Amostra de perfis pequena (27 no diagnóstico salvo), com mais da metade classificada como ruído; a leitura por "grupo de
  perfil" é frágil.
- `cluster_score` vem do algoritmo inteiro, não de cada linha: valores praticamente iguais entre linhas do mesmo formato são
  esperados (nota de interpretação em `gold_clusters.ipynb`).
- As componentes principais de reel e de feed têm cargas diferentes (feed não tem `videoPlayCount`/`videoDuration`), então
  um `cluster_label` de reel e um de feed não são comparáveis entre si.
- Os clusters de perfil (padrão de engajamento do perfil inteiro) e os de conteúdo (posts individuais) são espaços
  diferentes; cruzá-los é uma pergunta que nenhuma das duas tabelas responde sozinha (nota de interpretação em
  `gold_profile_clusters_engagement.ipynb`).
- Clusterização de perfis e matriz de quadrantes coexistem como visões distintas; um não substitui o outro (ADR 0018,
  Consequências).
- A coleta não captura compartilhamentos e salvamentos (ADR 0018), portanto não entram em nenhuma feature.

## Vínculos

- Código: [`src/modeling/clustering.py`](../../src/modeling/clustering.py), [`src/modeling/profile_clustering.py`](../../src/modeling/profile_clustering.py), [`src/modeling/pca.py`](../../src/modeling/pca.py), [`src/modeling/config.py`](../../src/modeling/config.py), [`src/modeling/orchestration.py`](../../src/modeling/orchestration.py)
- ADR: [0018](../adr/0018-realinhar-engajamento-e-matriz-de-quadrantes-ao-relatorio-vhl-sem-produto-deputados.md), [0020](../adr/0020-alinhamento-tcc-funil-cobra-race-nsm-ice-cmgr-e-reformulacao-do-dashboard-de-growth.md) (Fichas 1 e 2), [0003](../adr/0003-desacoplar-modelagem-do-notebook-via-scripts-cli-com-checkpoint.md) (checkpoint do PCA e do cluster), [0001](../adr/0001-separar-modelagem-em-etapas-deterministicas-e-refinamento-manual.md)
- Notebooks: [`03_modelagem_hibrida.ipynb`](../../notebooks/03_modelagem_hibrida.ipynb), [`gold_clusters.ipynb`](../../notebooks/diagnostico_medallion/gold_clusters.ipynb), [`gold_profile_clusters_engagement.ipynb`](../../notebooks/diagnostico_medallion/gold_profile_clusters_engagement.ipynb)
- TCC (capítulo/seção): a preencher
