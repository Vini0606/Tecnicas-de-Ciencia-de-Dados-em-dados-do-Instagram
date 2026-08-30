---
status: accepted
---

# Organizar a landing zone por `run_id`, não por entidade

## Contexto

A ADR 0011 introduziu a landing zone (JSON bruto por `run_id`, sem schema, anterior à Bronze) mas
não especificou a ordem de aninhamento de pastas. A implementação (PR #32,
`src/data_extract/ingestion.py::archive_raw_json`) escolheu `<landing_dir>/<entidade>/<run_id>.json`
-- uma pasta por entidade (`profiles/`, `posts/`, `reels/`), com o `run_id` só no nome do arquivo.

Numa sessão de `/grill-with-docs`, surgiu a pergunta de se esse layout atende a necessidade real de
"cruzar" os três arquivos de uma mesma execução depois. Investigando: o `run_id` já está presente no
nome de cada um dos três arquivos, então cruzar por nome (`find data/landing -name "$RUN_ID*"`) já
funciona hoje, independente da ordem de aninhamento. A necessidade real identificada foi outra:
poder **apagar ou arquivar tudo de uma execução com uma operação só** (ex: `rm -rf
landing/<run_id>/`) -- isso o esquema atual não permite, porque os três arquivos de uma run ficam
espalhados em três pastas de entidade diferentes.

## Decisão

Trocar o layout da landing zone para `<landing_dir>/<run_id>/<entidade>.json` -- pasta por `run_id`,
arquivo por entidade dentro dela.

A limpeza/arquivamento de runs antigas continua **manual e ocasional** por enquanto -- nenhum
mecanismo de retenção automática (manter só os últimos N runs, expirar por idade) é implementado
nesta decisão. Segue o mesmo raciocínio que a ADR 0011 já usou para adiar outras peças (histórico de
Gold, propagação de parâmetros para a lambda): a landing zone ainda não rodou num regime contínuo de
produção, então uma política de retenção automática agora seria design especulativo.

O único run já arquivado no esquema antigo (do teste E2E real da ADR 0012,
`data/landing/{profiles,posts,reels}/a8f36a6f-....json`) não é migrado -- fica como está, dado de um
teste de validação, não de produção contínua.

Junto, corrige uma inconsistência encontrada na mesma investigação: `scripts/run_apify_backfill.py`
gerava `run_id` com `uuid.uuid4()` puro, sem timestamp, diferente de `build_run_id()` (`src/run_id.py`,
já usado por `pipeline.py` e pelas lambdas), que prefixa `YYYYMMDD_HHMMSS_`. Isso fazia `data/landing/`
acumular uma mistura de pastas ordenáveis cronologicamente por nome e pastas que não são -- o mesmo
problema de usabilidade que motivou esta ADR. `run_apify_backfill.py` passa a usar `build_run_id()`
também, unificando o formato em todos os pontos de entrada que escrevem na landing zone.

Também corrige uma lacuna de `.gitignore` encontrada na mesma investigação: `data/landing/`,
`data/backfill/` (relatórios de `run_apify_backfill.py`) e `data/calibration/` (saída de
`run_apify_calibration_test.py`) nunca tinham entrada própria no `.gitignore` -- ao contrário de
`data/raw/`, `data/bronze/`, `data/silver/`, `data/gold/` e `data/model_checkpoints/`, que já eram
ignoradas. Isso não tinha causado problema até agora porque nenhuma execução real desses scripts
tinha gerado dado de verdade para vazar. As três entradas são adicionadas ao `.gitignore` nesta ADR.

## Por que

**Apagar/arquivar por execução é a necessidade real, e só o layout novo resolve isso.** Cruzar por
`run_id` já funcionava com o layout antigo (via nome de arquivo); reorganizar só por causa disso não
adicionaria capacidade nova. Tratar "uma execução" como a unidade atômica de limpeza/arquivamento --
alinhado com o `run_id` já ser o conceito central em todo o resto do projeto (Bronze carimba
`_run_id` em cada linha, os checkpoints de modelagem são uma pasta por `run_id`) -- é o que
justifica a mudança.

**Nenhuma capacidade existente é perdida.** Listar todos os `profiles.json` históricos ao longo do
tempo continua igualmente simples com o layout novo (`find data/landing -name profiles.json`) --
não há assimetria real entre os dois esquemas para leitura/correlação, só para apagar.

## Opções consideradas

- **Manter o layout por entidade** (`<entidade>/<run_id>.json`) -- rejeitada: não atende a
  necessidade real (apagar/arquivar uma run inteira exige acertar três pastas, não uma).
- **Implementar já uma política de retenção automática** junto com a reorganização -- rejeitada por
  ora: nenhum uso real em regime contínuo ainda existe para informar os parâmetros dessa política
  (quantas runs manter, por quanto tempo); decisão especulativa demais nesta fase.
- **Migrar o run já arquivado no esquema antigo** -- rejeitada: é dado de um teste de validação
  pontual, não de produção; forçar consistência retroativa aqui é escopo extra sem necessidade
  concreta.

## Consequências

- `archive_raw_json` passa a construir `<landing_dir>/<run_id>/<entidade>.json` em vez de
  `<landing_dir>/<entidade>/<run_id>.json`. Testes (`test_ingestion.py`, `test_pipeline.py`,
  `test_extract_lambda.py`) atualizados para o novo layout.
- O único run já arquivado no esquema antigo (`data/landing/{profiles,posts,reels}/a8f36a6f-....json`,
  do teste E2E da ADR 0012) fica órfão do padrão novo -- não é um problema funcional (nenhum código
  lê a landing zone de volta), só uma inconsistência histórica esperada e documentada aqui.
- Apagar/arquivar uma execução específica vira uma operação de filesystem de um passo
  (`rm -rf data/landing/<run_id>/`), sem automação nenhuma por trás -- fica como trabalho futuro
  quando o monitor contínuo (ADR 0011) tiver volume real de runs acumulado.
- `scripts/run_apify_backfill.py` passa a importar `build_run_id` de `src/run_id.py` em vez de
  `uuid` diretamente. O `run_id` do teste E2E da ADR 0012 (`a8f36a6f-...`, sem timestamp) fica como
  o único exemplo do formato antigo -- não é migrado, mesmo raciocínio do item acima.
- `.gitignore` ganha `data/landing/`, `data/backfill/` e `data/calibration/`.
