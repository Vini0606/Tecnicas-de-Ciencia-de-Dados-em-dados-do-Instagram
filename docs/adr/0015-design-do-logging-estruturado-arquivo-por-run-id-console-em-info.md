---
status: accepted
---

# Design do `logging` estruturado: arquivo por `run_id`, console em INFO, captura do logger interno do BERTopic

## Contexto

A ADR 0012 fechou o *quando* e o *porquê* do `logging` estruturado: é um pré-requisito explícito
antes de avançar a ADR 0011 rumo ao regime de extração incremental automatizada (o "monitor
contínuo"), mas não define o *como*. Esta ADR fecha o design, decidido numa sessão de
`/grill-with-docs` com o usuário, pergunta a pergunta.

Levantamento do estado atual antes de desenhar: nenhum módulo usa `logging` padrão hoje.
`pipeline.py` tem 4 `print()`s de estágio (`[1/3] BRONZE`, `[2/3] SILVER`, `[3/3] GOLD`,
`[MODELAGEM]`); `run_deterministic_modeling` (PCA → clustering → sentimento → tópicos) não imprime
nada próprio. A granularidade por sub-etapa do BERTopic que a ADR 0012 observou
(`BERTopic - Embedding/Dimensionality/Cluster/Representation - ...`) já vem de `logging` padrão do
Python (`logging.getLogger("BERTopic")`, não `print()`), configurado internamente pelo BERTopic com
seu próprio `StreamHandler` e `propagate=False` -- ou seja, hoje essas mensagens só existem no
console e nunca chegariam a um arquivo nosso, mesmo com um `logging` raiz configurado.

Também foi confirmado no código-fonte do BERTopic (`_bertopic.py`, `_reduce_topics`) a causa exata
do achado "segunda passada de representação parece redundante" da ADR 0012: quando `nr_topics` já é
maior ou igual ao número atual de tópicos (redução seria um no-op), o BERTopic **ainda assim** chama
`_extract_topics` de novo, recalculando a representação inteira -- é um comportamento incondicional
da biblioteca, não uma suposição.

## Decisão

1. **Um arquivo de log por `run_id`, não por invocação de processo.** Uma execução de
   `pipeline.py --run-modeling` gera dois `run_id`s (extração e modelagem, ADR 0001: "um run_id = um
   estado imutável", a modelagem nunca reaproveita o `run_id` da extração) e, portanto, dois
   arquivos de log.
2. **Diretório dedicado `data/logs/<run_id>/`**, separado de `data/landing/<run_id>/` (JSON bruto,
   ADR 0011/0014) e `data/model_checkpoints/<run_id>/` (artefatos de modelagem, ADR 0003) -- log
   operacional não é dado de negócio, e mantê-los separados facilita vasculhar logs de várias
   execuções sem entrar em diretórios com propósito de dado já documentado.
3. **Formato texto simples**, não JSON estruturado. Não há hoje nenhum consumidor programático dos
   logs (dashboard, alerta); estruturar em JSON agora seria projetar para um consumidor que ainda
   não existe. Migrar de texto para JSON depois, se o monitor contínuo precisar de agregação
   automática, é uma mudança de formatter isolada.
4. **Console em INFO, arquivo em DEBUG.** Console mantém o mesmo volume que os `print()`s de hoje
   (4 mensagens de estágio); o arquivo captura tudo, incluindo o detalhe fino por sub-etapa do
   BERTopic, para leitura pós-execução sem supervisão em tempo real.
5. **O handler de arquivo troca (swap), não acumula, quando o `run_id` muda no meio do processo**
   (extração → modelagem dentro de `pipeline.py --run-modeling`). O handler de arquivo da extração é
   removido no momento exato em que o `run_id` da modelagem é cunhado (dentro de
   `run_deterministic_modeling`, via `build_run_id`) e um novo handler é anexado para o novo
   `run_id` -- reforça a fronteira "1 run_id = 1 estado imutável" também no log, não só nos dados.
   Como o `run_id` da modelagem só existe a partir desse ponto, quem o cunha (`run_deterministic_modeling`)
   é quem tem que anexar seu próprio handler -- o `__main__` de `pipeline.py` só consegue fazer isso
   de antemão para o `run_id` da extração, que já é conhecido antes de qualquer trabalho começar.
6. **Instrumentação do BERTopic** em `src/modeling/topics.py::model_topics`:
   - Anexar o handler de arquivo (DEBUG) diretamente em `logging.getLogger("BERTopic")` -- não dá
     pra confiar em propagação para o logger raiz, porque o BERTopic desliga `propagate` ao se
     configurar. O `StreamHandler` próprio do BERTopic continua intocado; o console continua exibindo
     o play-by-play exatamente como hoje.
   - Antes de chamar `topic_model.reduce_topics(...)`, checar explicitamente se vai ser um no-op
     (`len(topic_model.get_topics()) <= config.nr_topics`) e logar em DEBUG o resultado dessa
     checagem, cronometrando a chamada -- torna visível, com dado real de tempo, o custo da segunda
     passada de representação redundante (achado da ADR 0012, correção deliberadamente fora de
     escopo aqui).
7. **Escopo: só `pipeline.py` e `src/modeling/*`.** Não inclui `scripts/run_apify_backfill.py`,
   `scripts/run_apify_calibration_test.py`, `scripts/refine_topics.py`, nem
   `scripts/run_profile_clustering_engagement.py` -- são utilitários manuais, sempre exigem `--yes`
   explícito, e não têm nenhuma perspectiva de rodar desacompanhados. Só o caminho que
   `run_medallion_pipeline` exercita é o que a ADR 0012 amarra como pré-requisito (o que vai rodar
   sem supervisão no monitor contínuo da ADR 0011).

## Por que

**Cada decisão de design segue de algo que o projeto já estabeleceu, não de uma preferência nova.**
Log por `run_id` (decisão 1) e o swap de handler (decisão 5) seguem diretamente do conceito de
"run_id = estado imutável" que já organiza Bronze/Silver/Gold e os checkpoints (ADR 0001/0003).
Formato texto simples (decisão 3) e o escopo restrito (decisão 7) seguem do princípio de não
generalizar/instrumentar além do que o problema atual pede (mesmo espírito da ADR 0004) -- a ADR
0012 amarrou o gatilho a uma necessidade concreta (monitor contínuo), não a "logging bonito em todo
lugar".

**A captura do logger do BERTopic (decisão 6) resolve um problema real e específico, não
hipotético.** A ADR 0012 só conseguiu ver o achado da segunda passada de representação porque uma
pessoa leu o console em tempo real -- exatamente o cenário que deixa de existir no monitor contínuo.
Sem capturar esse logger explicitamente, a granularidade por sub-etapa do BERTopic simplesmente não
sobreviveria a uma execução não supervisionada, mesmo com um `logging` nosso bem desenhado ao redor.

## Opções consideradas

- **Log por invocação de processo, não por `run_id`** -- rejeitada: mais fácil de acompanhar "o que
  aconteceu quando rodei", mas quebra a equivalência "1 run_id = 1 artefato" que o resto do projeto
  já usa.
- **Log dentro dos diretórios de artefato existentes (`data/landing/<run_id>/`,
  `data/model_checkpoints/<run_id>/`)** -- rejeitada: mistura log operacional com diretórios que já
  têm propósito de dado documentado (JSON bruto / checkpoint), dificultando separar "o que é
  artefato de negócio" de "o que é rastro de execução".
- **JSON lines desde já** -- rejeitada por ora: não há consumidor programático hoje; estruturar
  agora seria projetar para uma necessidade futura não confirmada.
- **Os dois handlers (console e arquivo) em DEBUG** -- rejeitada: polui o console com detalhe que
  ninguém pediu pra ver em tempo real, contrariando a própria conclusão da ADR 0012 de que o volume
  atual de `print()`s já era suficiente para observação supervisionada.
- **Acumular handlers de arquivo em vez de trocar** -- rejeitada: mais simples de implementar (nunca
  remove handler), mas borra a fronteira entre `run_id`s que o projeto trata como estrita em todo o
  resto do sistema.
- **Converter `print()` para `logging` em todos os scripts, não só `pipeline.py`/`src/modeling`** --
  rejeitada por ora: expande escopo além do que a ADR 0012 exige; os scripts utilitários manuais não
  têm perspectiva de rodar sem supervisão.

## Consequências

- Novo módulo (nome a definir na implementação, ex: `src/logging_setup.py`, seguindo o padrão de
  utilitário singular já usado por `src/run_id.py`) expõe a configuração do handler de console
  (INFO, uma vez por processo) e uma função para anexar/trocar o handler de arquivo por `run_id`
  (DEBUG), incluindo a anexação direta em `logging.getLogger("BERTopic")`.
- `pipeline.py` (`__main__` e `run_medallion_pipeline`) e `src/modeling/*` (em particular
  `run_deterministic_modeling` e `model_topics`) trocam seus `print()` por chamadas a `logging`.
- `data/logs/` precisa de entrada no `.gitignore` (mesma lógica de `data/landing/`, `data/backfill/`,
  `data/calibration/`).
- Fica registrado como melhoria futura, fora de escopo aqui: converter os scripts utilitários
  manuais (`run_apify_backfill.py`, `run_apify_calibration_test.py`, `refine_topics.py`,
  `run_profile_clustering_engagement.py`) para `logging`, e corrigir (não só logar) a segunda
  passada de representação redundante do BERTopic.
