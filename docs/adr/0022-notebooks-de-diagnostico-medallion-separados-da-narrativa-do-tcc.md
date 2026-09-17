---
status: accepted
---

# Notebooks de diagnóstico Medallion, separados da narrativa do TCC, um por estágio Bronze/Silver e um por domínio de modelagem Gold

## Contexto

Os notebooks existentes (`01`-`03`, `05`-`07`) contam a narrativa do TCC — cada um documenta uma
etapa da história (extração, EDA, modelagem híbrida, conclusões, regressão de performance por
post). Não existe hoje nenhum lugar versionado para inspeção sistemática e aprofundada de cada
tabela que `pipeline.py` produz no Medallion: completude, distribuição, evolução temporal e
outliers de uma tabela Gold específica (engajamento, sentimento, tópicos de discurso, clusters,
métricas de crescimento, NSM) exigiam código ad-hoc fora de qualquer notebook.

Com 3 tabelas Bronze, 5 Silver e 9 saídas de modelagem em Gold (sem contar as `_history`), um
notebook por tabela física (~19) seria granularidade demais para manter — a maioria das tabelas
Silver é limpeza intermediária, sem profundidade analítica própria. Um único notebook gigante
cobrindo tudo, no outro extremo, misturaria estágios de ingestão com saídas de modelo que merecem
tratamento estatístico próprio.

## Decisão

- Novo diretório `notebooks/diagnostico_medallion/`, separado da sequência narrativa `01`-`07`, que
  fica intocada.
- **`00_bronze_silver_overview.ipynb`** — um único notebook consolidando as 3 tabelas Bronze + 5
  Silver (volumetria, nulos, duplicatas, o que a limpeza Silver remove/transforma em relação à
  Bronze). Não usa o esqueleto de 7 seções abaixo — reservado aos notebooks de domínio Gold.
- **Um notebook por domínio de modelagem em Gold**, nomeado 1:1 com a constante correspondente em
  `config.py`: `gold_engagement`, `gold_sentiment`, `gold_discourse_topics`,
  `gold_clusters`, `gold_profile_clusters_engagement`, `gold_growth_metrics`, `gold_nsm`.
  `post_performance` fica fora — já coberto por `06`/`07`. As tabelas `_history` entram como a
  seção de evolução temporal do notebook do domínio correspondente, não como notebook separado.
- Cada notebook de domínio Gold segue um esqueleto analítico comum: (1) carga via `DeltaRepository`
  + schema/dtypes; (2) completude (nulos, duplicatas, cobertura por governador/UF/partido); (3)
  distribuições univariadas das métricas-chave; (4) evolução temporal via a `_history` irmã, quando
  existir; (5) relações com covariáveis conhecidas (partido, UF, tipo de conteúdo); (6)
  outliers/casos extremos sinalizados explicitamente; (7) nota de interpretação curta.
- Acesso a dado via `DeltaRepository` sempre que a tabela estiver coberta por ele -- é o caso de
  toda leitura em Gold nos 7 `gold_*.ipynb`. Exceção conhecida, restrita a
  `00_bronze_silver_overview.ipynb` e a uma célula de `gold_clusters.ipynb`: `DeltaRepository` não
  expõe Bronze nem `profiles_clean`/`comments_clean` (Silver) diretamente -- essas leituras usam
  `BronzeWriter.get_latest_*` (mesmo seam que `pipeline.py` já usa para Bronze) e leitura direta via
  `deltalake.DeltaTable` (mesmo primitivo que `DeltaRepository._load` usa por baixo), nunca um
  terceiro jeito de acessar Delta. Em todos os casos os notebooks são estritamente leitura, nunca
  chamam `run_medallion_pipeline`, `run_deterministic_modeling` ou qualquer writer/aggregator/
  cleaner. Mesmo princípio que a ADR
  [0003](0003-desacoplar-modelagem-do-notebook-via-scripts-cli-com-checkpoint.md) já estabeleceu:
  notebook é instrumentação de leitura, nunca gatilho de escrita.
- Cálculos repetidos entre os notebooks (resumo de completude, join com `governors_metadata` para
  partido/UF) vivem num módulo Python testável em `src/`, não copiados por notebook.

Spec completo (user stories, decisões de implementação e teste) em
[issue #128](https://github.com/Vini0606/Tecnicas-de-Ciencia-de-Dados-em-dados-do-Instagram/issues/128).

## Por que

A granularidade por domínio de modelagem em Gold (em vez de por tabela física) espelha como
`src/modeling/*.py` já é organizado e como `06`/`07` já fazem para regressão — cada domínio tem sua
própria lógica estatística e merece profundidade própria, sem competir por espaço com os outros.
Bronze/Silver, por outro lado, não têm essa profundidade individualmente (são limpeza, não modelo),
então cabem consolidados num único notebook por estágio. Separar do `01`-`07` evita misturar dois
propósitos diferentes — narrativa do TCC (prosa, para o leitor final) vs. instrumentação de
diagnóstico (para o autor, durante o desenvolvimento) — na mesma sequência numerada.

## Opções consideradas

- **Um notebook por tabela física (~19, incluindo `_history`)** — rejeitada: granularidade
  excessiva para tabelas Silver que são só limpeza intermediária, sem conteúdo analítico próprio;
  27 notebooks a manter seria maior custo do que benefício.
- **Um notebook único cobrindo Bronze+Silver+Gold** — rejeitada: misturaria estágios de ingestão
  com saídas de modelo de naturezas muito diferentes, perdendo a chance de cada domínio Gold ter o
  tratamento estatístico específico que merece.
- **Um notebook por estágio Medallion (3: Bronze, Silver, Gold)** — rejeitada isoladamente, mas
  parcialmente incorporada: Bronze e Silver, de fato, cabem consolidados (pouca profundidade
  individual), mas um único notebook "Gold" perderia a granularidade por domínio que o pedido
  original ("análises mais aprofundadas em todas as modelagens") pedia.
- **Misturar estes notebooks na sequência numerada `01`-`07`** — rejeitada: são instrumentação de
  trabalho, não capítulos da narrativa do TCC; numerá-los junto arriscaria confundir os dois
  propósitos e complicar renumeração futura da narrativa.

## Consequências

- `notebooks/diagnostico_medallion/` cresce independente da narrativa do TCC — não precisa ficar
  sincronizado com a numeração `01`-`07`.
- Qualquer nova tabela Gold futura precisa de uma decisão consciente: vira um `gold_*.ipynb` novo,
  ou é pequena/derivada o suficiente para caber dentro de um domínio já existente.
- O módulo compartilhado em `src/` (completude, join com `governors_metadata`) precisa ser mantido
  deliberadamente mínimo — o risco de virar um framework de diagnóstico genérico não solicitado
  existe se crescer além do que os ~8 notebooks de fato repetem.
