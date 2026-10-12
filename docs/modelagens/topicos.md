# Tópicos de discurso e de comentário (BERTopic)

**Status:** a documentar
**Atualizada em:** 2026-10-11

> Justificativa do status: o método está em uso e a decisão de arquitetura está registrada (ADR 0001, 0003, 0020), mas não há
> registro de avaliação da qualidade dos tópicos (coerência, comparação com outro método ou revisão manual). O que existe é
> diagnóstico de tabela e uma auditoria de rótulos (ADR 0038) que apontou problemas de legibilidade, contornados na
> apresentação, não no modelo.

## Pergunta de negócio

- **Comentários:** sobre o que o público fala nos comentários de cada governador, e com que sentimento? Resultado exibido como
  **Grupo de comentários**, separado em positivos e negativos (`CONTEXT.md`).
- **Discurso:** de que assuntos a própria assessoria fala nas legendas (e nas falas transcritas dos reels)? Cada assunto,
  depois de rotulado, é uma **Pauta**, a unidade da fila de "O que produzir" (`CONTEXT.md`). O contraste entre as duas fontes
  (fala da assessoria x reação do público) é o que o TCC propõe (ADR 0020, Decisão 4).
- **Captions como preditor:** o tema da legenda de um post entra como preditor na regressão de performance por post (ver
  [regressao-performance-post.md](regressao-performance-post.md)).

## Dados e série

Três usos do BERTopic, com corpora diferentes (`src/modeling/config.py`, `src/modeling/orchestration.py`):

| Uso | Corpus | Tabela Gold | `nr_topics` | HDBSCAN (`min_cluster_size` / `min_samples`) |
|---|---|---|---|---|
| Comentários | comentários de reels e de posts de feed, pré-processados (sem stopwords, emojis convertidos em texto) | `governor_sentiment` (colunas `Topic`, `Name`) | 50 | 15 / 5 |
| Discurso oficial | legenda (`caption`, posts) e transcrição (`transcript`, reels), um único modelo para as duas fontes | `governor_discourse_topics` | `"auto"` | 5 / 2 |
| Captions de post (preditor) | `caption` + `hashtags` dos posts estáticos | não persiste tabela de tópicos própria; a coluna `Topic` alimenta a regressão | 15 | 5 / 2 |

- Embedding comum às três: `rufimelo/bert-large-portuguese-cased-sts`, `language="multilingual"`, tokenização do
  `CountVectorizer` que preserva emojis como tokens (`EMOJI_TOKEN_PATTERN`).
- Comentários de reels e de posts são combinados antes da modelagem e deduplicados por `id_comment`, preferindo a linha de
  reel (`combine_comment_sources`, ADR 0034). `governor_sentiment.id_reel` passa a significar "id da publicação comentada".
- Tabelas separadas para as duas fontes porque são granularidades conceitualmente distintas: fala da assessoria x reação do
  público (ADR 0020, Opções consideradas). Os ids de `Topic` das duas tabelas pertencem a espaços diferentes e não devem ser
  confundidos (cabeçalho de `notebooks/diagnostico_medallion/gold_discourse_topics.ipynb`).
- Tamanho do corpus de discurso: a ADR 0020 estima cerca de 810 legendas/transcrições na coleta da época; o diagnóstico salvo
  tem 694 linhas em `governor_discourse_topics` (277 sem texto, 39,9%). O corpus de comentários cresce com o volume coletado
  (ADR 0034). Para a Coleta final (90 dias, #256) o tamanho não está registrado.
- Limite: o Instagram devolve só uma amostra dos comentários mais recentes por publicação (`latestComments`, 10 por reel,
  amostra e não total; `docs/research/apify-instagram-actors-cobra-mapping.md`).

## Método escolhido

1. **Etapa determinística** (`run_deterministic_modeling`, ADR 0001): `model_topics` ajusta o `BERTopic` com HDBSCAN
   (`metric="euclidean"`, `cluster_selection_method="eom"`) e `KeyBERTInspired` como representação, depois `reduce_topics` até
   `nr_topics`. Com `nr_topics="auto"`, o BERTopic mescla só tópicos redundantes, sem forçar uma contagem alvo: volume baixo
   pode legitimamente gerar menos de 50 tópicos (docstring de `DiscourseTopicModelConfig`; ADR 0020, Ficha 4).
2. **Refinamento manual dos rótulos via Gemini** (`refine_topics_with_gemini`, `scripts/refine_topics.py`): chamada separada,
   com `topic_model.update_topics(..., representation_model=GeminiDocsRefiner(...))`, sem refazer embeddings nem
   clusterização. Para o discurso, o prompt pede um rótulo de no máximo 6 palavras (`DISCOURSE_PROMPT_TEMPLATE`); tópico sem
   palavra alguma recebe o rótulo fixo "sem assunto definido" (`DEGENERATE_TOPIC_LABEL`, issue #186). O refino continua
   manual e fora do `pipeline.py` (ADR 0034, Decisão 5).
3. **Checkpoint:** `run_deterministic_modeling` persiste o modelo ajustado em `data/model_checkpoints/<run_id>/` para o refino
   rodar em outro processo sem reprocessar os embeddings, cerca de 14 minutos (ADR 0003).
4. **Consumo:** o Score ICE de tópicos de comentário (`topic_priority_score`) e o ICE por pauta
   (`content_topic_priority_score`) derivam destas tabelas.
5. **Apresentação** (ADR 0038, `dashboard/core/rotulos.py`): tira o prefixo de id e troca `_` por vírgula; tópico em que pelo
   menos 75% das palavras são só descrição de emoji ganha nome por família ("Emojis de mãos e aplausos", "Reação só com
   emojis" etc.); menções `@usuario` de terceiros (8 caracteres ou mais) saem dos nomes. O texto bruto dos comentários no popup
   não é filtrado (ADR 0038, Consequências).

## Alternativas avaliadas

Só constam as alternativas registradas nos ADRs.

| Alternativa | Vantagem | Desvantagem | Resultado |
|---|---|---|---|
| `GeminiDocsRefiner` como `representation_model` do construtor (estado original) | Rótulo final em uma chamada | Chama o Gemini duas vezes por execução (em `fit_transform` e em `reduce_topics`); acopla uma API paga à etapa determinística (ADR 0001) | Rejeitada; `update_topics` após o ajuste |
| Uma função única `run_hybrid_modeling()` (ADR 0001) | Simples | Obrigaria reabrir o orquestrador para separar as etapas | Rejeitada |
| Checkpoint opcional por flag (ADR 0003) | Menos disco | Risco de esquecer de habilitar e perder a chance de refinar sem reprocessar | Rejeitada; persistência incondicional |
| Reconstruir `docs` relendo `governor_sentiment` (ADR 0003) | Menos artefatos | A ordem de leitura do Delta não é garantida igual à de escrita; risco de desalinhar `Topic` e `Name` sem erro visível | Rejeitada |
| Estender `governor_sentiment` com os tópicos de discurso (ADR 0020) | Uma tabela | Mistura granularidades (fala da assessoria x reação do público) | Rejeitada; tabela `governor_discourse_topics` |
| Forçar ~50 tópicos também no discurso (ADR 0020, Ficha 4) | Paridade com comentários | Corpus cerca de 15 vezes menor | Rejeitada; `nr_topics="auto"` |
| Proxy simples de tema para a regressão (comprimento de legenda + contagem de hashtags, ADR 0019) | Sem modelo de NLP novo | Menos fiel ao que o relatório da VHL pede | Rejeitada pelo autor; BERTopic sobre captions |
| Outros modelos de tópicos (LDA, NMF) ou outros embeddings | — | — | Não registrado |

## Validação

O que está registrado:

- **Tópicos de comentário** (`gold_sentiment.ipynb`, execução salva): a coluna `Topic` tem 50 valores distintos; há 694 linhas sem
  `Topic` e 694 sem `id_comment`. Provavelmente são as linhas de legenda/transcrição, que não recebem tópico de comentário
  (inferência a partir do código; o notebook não confirma).
- **Tópicos de discurso** (`gold_discourse_topics.ipynb`, execução salva): 12 nomes de tópico (de `-1` a `10`), nenhum com 2
  posts ou menos; 1 tópico sem nome refinado (`0____`), com 280 posts. O notebook interpreta nome vazio como tópico ainda sem refino via
  Gemini para aquele `_run_id`; o rótulo "sem assunto definido" para o tópico degenerado veio depois (issue #186, comentário em
  `topic_labels.py`).
- **Auditoria dos rótulos** (ADR 0038, 2026-10-08): os tópicos de comentário são quase todos emojis convertidos em palavras
  ("mãos aplaudindo pele clara", "tecla 3 tecla 2"); 28% dos comentários positivos de um governador apareciam com esse tipo de
  nome. Correção feita na camada de apresentação (`rotulos.py`), não no modelo. A heurística de emoji usa uma lista fixa de
  palavras e pode rotular como emoji um tópico de texto com muitos emojis (ADR 0038, Consequências).
- **Tópicos de captions** (`notebooks/07_regressao_performance_estatico.ipynb`, execução salva em 2026-09-05): 29 tópicos
  reduzidos para 15 sobre 300 posts. Esse notebook parece rodar sobre dado sintético (ver
  [regressao-performance-post.md](regressao-performance-post.md)), então o número não descreve os governadores reais.
- **PCA/BERTopic do notebook 03:** `notebooks/03_modelagem_hibrida.ipynb` tem mapa de distância intertópica, hierarquia e
  heatmap, mas sem saída salva; nenhuma métrica de coerência de tópico está registrada.
- Testes automatizados do código: `tests/test_topics.py`, `tests/test_refine_topics_script.py`.

## Limitações

- Sem métrica de qualidade registrada (coerência, estabilidade entre execuções, comparação com outro método).
- Os tópicos de comentário são dominados por emoji; o nome legível é um ajuste de apresentação, e o texto original do
  comentário permanece como ponto sensível de privacidade (ADR 0038, ADR 0037).
- O refino por Gemini é manual, depende de API paga e de revisão humana, e produz texto citável no TCC (ADR 0001). Sem o
  refino, parte dos nomes são listas de palavras-chave ou vazios.
- Corpus de discurso pequeno: poucos tópicos estáveis é um resultado esperado, não um erro (ADR 0020, Ficha 4).
- Cada reel pertence a uma única pauta, a da legenda (`CONTEXT.md`).
- O modelo de tópicos de captions só existe para posts estáticos: reels não têm `caption` no Bronze/Silver
  (`PostPerformanceConfig`, `src/modeling/config.py`).
- A modelagem pesada (embedding de ~14 min, ~2,5 GB de modelos) roda localmente, não na AWS (ADR 0039, Decisão 8).

## Vínculos

- Código: [`src/modeling/topics.py`](../../src/modeling/topics.py), [`src/modeling/topic_labels.py`](../../src/modeling/topic_labels.py), [`src/modeling/gemini_refiner.py`](../../src/modeling/gemini_refiner.py), [`src/modeling/preprocessing.py`](../../src/modeling/preprocessing.py), [`src/modeling/comment_sources.py`](../../src/modeling/comment_sources.py), [`src/modeling/config.py`](../../src/modeling/config.py), [`dashboard/core/rotulos.py`](../../dashboard/core/rotulos.py)
- ADR: [0001](../adr/0001-separar-modelagem-em-etapas-deterministicas-e-refinamento-manual.md), [0003](../adr/0003-desacoplar-modelagem-do-notebook-via-scripts-cli-com-checkpoint.md), [0019](../adr/0019-regressao-de-performance-por-post-video-e-estatico-com-lasso-e-bertopic.md), [0020](../adr/0020-alinhamento-tcc-funil-cobra-race-nsm-ice-cmgr-e-reformulacao-do-dashboard-de-growth.md), [0034](../adr/0034-pipeline-ponto-unico-ugc-no-extrator-comentarios-de-posts-janela-e-relatorio.md), [0038](../adr/0038-correcoes-da-auditoria-rotulos-amostra-minima-e-privacidade.md)
- Notebooks: [`03_modelagem_hibrida.ipynb`](../../notebooks/03_modelagem_hibrida.ipynb), [`gold_discourse_topics.ipynb`](../../notebooks/diagnostico_medallion/gold_discourse_topics.ipynb), [`gold_sentiment.ipynb`](../../notebooks/diagnostico_medallion/gold_sentiment.ipynb) (colunas `Topic`/`Name` dos comentários)
- TCC (capítulo/seção): a preencher
