---
status: accepted
---

# Separar a modelagem híbrida em etapas puras, com o refinamento de tópicos via Gemini isolado do lote determinístico

## Contexto

Hoje toda a modelagem (PCA → `AutoClusterHPO` → sentimento → BERTopic → refinamento de rótulos de tópico via `GeminiDocsRefiner`) vive em células sequenciais do notebook `notebooks/03_modelagem_hibrida.ipynb`, rodada manualmente do início ao fim. Não há artefatos de modelo versionados, não há teste da lógica de modelagem em si (só do writer, em `test_model_enricher.py`), e o refinamento via Gemini está acoplado ao `BERTopic` via `representation_model=GeminiDocsRefiner(...)` no construtor — o que faz o Gemini ser chamado duas vezes por execução (uma em `fit_transform`, outra em `reduce_topics`).

## Decisão

Extrair a lógica de modelagem para um novo pacote `src/modeling/` (consolidando também `AutoClusterHPO`, hoje em `src/analyzes/`), como funções puras por etapa — DataFrame(s) + config entram, DataFrame(s) + objeto do modelo saem, sem I/O de Delta dentro da função. Duas funções orquestradoras, não uma:

- `run_deterministic_modeling(df_reels, df_comments, config)` — PCA, `cluster_reels`, `analyze_sentiment`, `model_topics` (BERTopic instanciado **sem** `representation_model=GeminiDocsRefiner`, com um representation model determinístico como `KeyBERTInspired`). Não depende de revisão humana nem de API externa paga.
- `refine_topics_with_gemini(topic_model, docs, config)` — chamada separada e manual, via `topic_model.update_topics(docs, representation_model=GeminiDocsRefiner(...))`, que recalcula só as representações de tópico reaproveitando a clusterização já ajustada (sem refazer embeddings/UMAP/HDBSCAN).

Cada orquestrador escreve em Gold via `ModelEnricher` com seu próprio `run_id` novo — a etapa determinística grava rótulos de tópico provisórios; o refinamento sobrescreve com os rótulos finais numa segunda escrita (`write_delta` já é `overwrite` por padrão, então isso não exige mudança no writer).

## Por que

O notebook mistura uma etapa 100% automatizável (PCA/clustering/sentimento/topic modeling determinístico) com uma etapa que depende de uma API paga e, por envolver um LLM rotulando temas que viram texto citável no TCC, justifica revisão humana antes de aceitar o resultado. Separar isso agora, como parte da extração do notebook para `src/`, evita reabrir o orquestrador depois se/quando a parte determinística virar de fato um job agendado — e corrige, de brinde, a chamada duplicada ao Gemini que existe hoje.

## Opções consideradas

- **Uma função única `run_hybrid_modeling()`** chamando tudo em sequência — rejeitada: exigiria reabrir o orquestrador para separar as etapas mais tarde.
- **Manter `GeminiDocsRefiner` como `representation_model` do construtor do `BERTopic`** — rejeitada: `update_topics()` depois do `fit` permite separar sem duplicar a clusterização nem o custo de embeddings.
- **Escrever em Gold uma única vez, após as duas etapas** — rejeitada: como `write_delta` já é overwrite, nada impede duas escritas, e escrever após a etapa determinística entrega valor (resultado utilizável) antes do refinamento manual rodar.
- **Reaproveitar o mesmo `run_id` nas duas escritas** — rejeitada: quebraria a garantia de "um `run_id` = um estado imutável" que o resto do Medallion (Bronze/Silver/Gold) já mantém.
- **Colocar o código novo em `src/analyzes/` ou em `src/features/gold/`** — rejeitada: `src/analyzes/` não é um pacote de verdade (sem `__init__.py`, uma classe avulsa) e `src/features/` é reservado para lógica determinística de ETL já testada, com garantias diferentes das de uma etapa estocástica e dependente de API externa.

## Consequências

- `src/modeling/` passa a ser o único lugar com lógica de modelagem; o notebook 03 vira um driver fino que importa e chama essas funções, deixando de ser a fonte da lógica.
- Cada rodada de modelagem completa produz dois `run_id`s em Gold (determinístico + refinamento) em vez de um — ao reproduzir um número específico do TCC via `DeltaRepository(as_of_version=...)`, é preciso saber que existem duas versões em sequência, não uma.
- Habilita, mas não implementa, a automação da etapa determinística como job agendado — essa é uma decisão em aberto, não coberta por este ADR.
