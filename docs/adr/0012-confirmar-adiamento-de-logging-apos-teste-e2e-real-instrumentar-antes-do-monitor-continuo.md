---
status: accepted
---

# Confirmar o adiamento de `logging` estruturado após o primeiro teste E2E real; instrumentar antes do monitor contínuo (ADR 0011)

## Contexto

A ADR 0010 (branch `worktree-adr-0010-logging-decision`, ainda não mergeada em `main`) decidiu adiar
a implementação de `logging` estruturado até que uma execução real do pipeline informasse onde a
instrumentação realmente importa -- "rodar primeiro, instrumentar depois". Essa execução real
aconteceu nesta sessão (issue #33): uma extração real e paga via `scripts/run_apify_backfill.py
--days 1` (a primeira chamada real à Apify do projeto através dos scripts consolidados pela ADR
0011/PR #32), seguida de `pipeline.py --run-modeling` completo (Bronze → Silver → Gold →
PCA/clustering/sentimento/tópicos), rodados num ambiente limpo simulado dentro do próprio `main`
(backup de `data/` preservado em `data_backup_20260830_152309/`, fora do git).

A pergunta que esta ADR responde: agora que o dado real existe, a decisão de adiar `logging` da ADR
0010 se sustenta, ou os resultados desta execução mudam o cálculo?

## O que a execução real mostrou

- **Corretude**: Bronze recebeu 27 perfis, 195 posts, 140 reels via append; Silver deduplicou
  corretamente (26/191/136 -- a pequena queda é limpeza/dedup esperada, não perda de dado); Gold
  gerou `governor_engagement` (26), `governor_sentiment` (1760, uma linha por comentário) e
  `governor_clusters` (136, uma linha por reel) sem erro. `_bronze_has_data` funcionou como esperado
  e não reextraiu.
- **Timing**: pipeline completo em ~10,5 minutos ponta-a-ponta, sem GPU. Bronze (cache-hit) e
  Silver/Gold: segundos. PCA + `AutoClusterHPO` (300 trials): ~2-3s. Sentimento (carga do modelo +
  inferência): ~3min. BERTopic -- o estágio mais caro: embedding 5min02s, redução de
  dimensionalidade 14s, clustering <1s, representação de tópicos 28s + **mais 1min41s numa segunda
  passada de representação que rodou mesmo depois do próprio log dizer que a redução de tópicos era
  desnecessária** (44 tópicos já abaixo do teto de 50) -- achado registrado abaixo, não corrigido
  aqui.
- **Custo**: a extração real custou centavos de dólar, como estimado. Mas a taxa calibrada real
  (7,22 posts/governador/dia, 5,19 reels/governador/dia) ficou ~2,8x-3,1x acima do baseline usado em
  `apify_backfill_shared.estimate_cost_usd` (2,60 e 1,65) -- ou seja, a estimativa de custo mostrada
  antes do `--yes` de qualquer execução futura tende a **subestimar em ~3x** o custo real de uma
  janela maior. Achado registrado, não corrigido aqui.
- **Observação manual foi suficiente**: acompanhar os `print()`s existentes (com a saída também
  redirecionada a arquivo via `tee`, por precaução, sem ser um sistema de `logging`) foi suficiente
  para narrar o progresso e para descobrir os dois achados acima -- nenhum deles exigiu um nível de
  detalhe (DEBUG, timestamps por sub-etapa) que os `print()`s + os logs internos do próprio BERTopic
  não já oferecessem.

## Decisão

1. **A decisão da ADR 0010 se confirma para execuções supervisionadas como esta.** Não implementar
   `logging` estruturado agora. Uma execução manual, única, observada em tempo real por uma pessoa
   (ou pelo assistente, narrando ao usuário) continua não precisando de níveis de log, handler de
   arquivo por `run_id`, ou rotação -- os `print()`s existentes, combinados com o logging interno que
   o BERTopic já emite (`BERTopic - Embedding/Dimensionality/Cluster/Representation - ...`), já
   permitiram identificar os dois achados de timing/custo acima sem nenhuma instrumentação nova.
2. **Mas a decisão passa a ter uma condição de expiração explícita**: `logging` estruturado deve ser
   implementado **antes** de qualquer execução automatizada/agendada e não supervisionada do
   pipeline -- ou seja, antes de avançar a ADR 0011 para o regime "incremental automatizável" (cron,
   lambda, ou qualquer execução sem alguém lendo o console em tempo real). Nesse regime, não existe
   "alguém observando os prints" para notar uma falha ou uma lentidão anômala -- é exatamente o
   cenário que a ADR 0010 explicitamente not tratou.
3. Quando esse `logging` for implementado, o design mínimo continua o mesmo que a ADR 0010 já
   esboçou (INFO para o que os `print()`s já mostram, DEBUG para detalhe adicional, handler de
   arquivo por `run_id`), **acrescido de**: granularidade DEBUG por sub-etapa do BERTopic (embedding,
   dimensionalidade, clustering, representação -- inclusive contabilizando explicitamente se uma
   segunda passada de representação por redução de tópicos foi de fato necessária), já que essa foi
   a única lentidão desta execução que exigiu leitura manual e atenta do log para ser percebida.

## Por que

**A ADR 0010 estava certa em adiar, e o teste real confirma isso em vez de contradizê-lo.** O medo
que justificaria implementar `logging` antes de rodar -- não saber onde o tempo é gasto, não
conseguir diagnosticar uma falha -- não se concretizou. Os `print()`s existentes mais o log nativo do
BERTopic já deram visibilidade suficiente para produzir a tabela de timing acima e para encontrar
dois achados reais (a segunda passada de representação redundante, e o baseline de custo
desatualizado). Implementar um sistema de `logging` agora, retroativamente, não teria mudado nenhuma
dessas descobertas.

**O que muda o cálculo não é "já rodamos uma vez", é "quem vai estar olhando da próxima vez".** A ADR
0010 foi desenhada em torno de uma pessoa observando uma execução manual. A ADR 0011 aponta
explicitamente para um "monitor contínuo" com um regime de extração incremental automatizável -- ou
seja, execuções sem ninguém olhando o console. Nesse regime, um `print()` que ninguém lê é
informação perdida; a lacuna que a ADR 0010 conscientemente deixou aberta ("resolve um problema
diferente: análise posterior, comparação entre execuções, depuração sem supervisão em tempo real")
deixa de ser hipotética e passa a ser exatamente o modo de operação pretendido.

**Achado do BERTopic reforça o design futuro, não a necessidade imediata.** A segunda passada de
representação (~1min41s aparentemente desnecessária) só foi percebida porque alguém leu o log
inteiro manualmente logo depois da execução. Numa execução não supervisionada, esse tipo de
ineficiência ficaria invisível indefinidamente -- é exatamente o tipo de coisa que uma métrica
DEBUG por sub-etapa, gravada em arquivo, tornaria visível sem exigir leitura manual toda vez.

## Opções consideradas

- **Implementar `logging` agora, com o dado real em mãos** -- rejeitada: o dado real mostrou que a
  visibilidade já era suficiente para esta execução supervisionada; instrumentar agora resolveria um
  problema (execução não supervisionada) que ainda não existe no projeto.
- **Reafirmar a ADR 0010 sem nenhuma condição nova** -- rejeitada: deixaria a decisão de quando
  revisitar `logging` implícita de novo, e o projeto já tem uma ADR (0011) apontando concretamente
  para quando essa condição deixa de valer (o monitor contínuo automatizado). Fica mais claro e
  rastreável amarrar a expiração da decisão a essa outra ADR do que deixá-la em aberto de novo.

## Consequências

- Nenhuma mudança de código de `logging` nesta tarefa -- só esta ADR, o backfill real
  (`run_id: a8f36a6f-4644-4588-be24-5bb53d564c57`) e a execução de modelagem
  (`run_id: 20260830_190146_bffaff02`), ambos já persistidos em `data/backfill/` e
  `data/model_checkpoints/` respectivamente.
- `logging` estruturado (INFO/DEBUG, handler de arquivo por `run_id`, granularidade extra por
  sub-etapa do BERTopic) vira um pré-requisito explícito e registrado para avançar a ADR 0011 rumo
  ao regime de extração incremental automatizável -- não uma melhoria futura solta, um bloqueador
  conhecido dessa transição específica.
- Dois achados de comportamento ficam registrados para decisão futura, sem correção nesta tarefa:
  (1) `BronzeWriter.get_latest_profiles`/`get_latest_posts`/`get_latest_reels` não filtram "mais
  recente" apesar do nome -- retornam a tabela Delta inteira, o dedup real acontece só no Silver via
  `deduplicate_latest`; (2) `apify_backfill_shared.estimate_cost_usd` usa um baseline
  (`BASELINE_POSTS_PER_DAY`/`BASELINE_REELS_PER_DAY`) que a taxa calibrada desta execução real
  mostrou estar ~2,8x-3,1x abaixo do valor real, subestimando o custo projetado de janelas maiores;
  (3) a segunda passada de fine-tuning de representação do BERTopic parece rodar mesmo quando a
  redução de tópicos é um no-op, custando ~1min41s sem necessidade aparente.
