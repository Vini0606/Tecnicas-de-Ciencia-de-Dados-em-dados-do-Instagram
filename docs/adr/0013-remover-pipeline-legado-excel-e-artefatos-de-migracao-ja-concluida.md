---
status: accepted
---

# Remover o pipeline legado Excel (`all.xlsx`) e os artefatos da migração já concluída para o Delta

## Contexto

O projeto tem, desde as Fases 1-3, um pipeline pré-Medallion baseado em Excel (`legacy/pipeline_legacy.py`
gerando `data/processed/all.xlsx` via `ExcelDataRepository`) e um utilitário de migração única
(`legacy/migrate_to_medallion.py`, duplicado em `scripts/migrate_to_medallion.py`) que puxava esse
Excel para as tabelas Delta da arquitetura Medallion atual. `pipeline.py` também mantinha um branch
intermediário (`_raw_has_data`/`_load_raw_data`) que migrava `data/raw/{profiles,posts,reels}.json`
locais para a Bronze quando não havia cache.

O teste E2E real desta sessão (ADR 0012, issue #33) confirmou que a Medallion (Bronze/Silver/Gold em
Delta, alimentada pelos scripts consolidados da ADR 0011) já é a fonte de verdade do projeto,
funcionando ponta-a-ponta com dado real. A migração única do Excel/JSON legado para o Delta já
aconteceu -- a Bronze de produção já contém esse dado. O próprio `legacy/README.md` já dizia
explicitamente: "não é necessário executar esses scripts para usar o dashboard atual".

## Decisão

Remover integralmente:

1. `legacy/` (pasta inteira: `pipeline_legacy.py`, `migrate_to_medallion.py`, `README.md`).
2. `scripts/migrate_to_medallion.py` (duplicata byte-a-byte do arquivo em `legacy/`).
3. `src/repositories/excel_repository.py` (`ExcelDataRepository`, usado só pelo pipeline legado).
4. `src/data_extract/readers.py` (`JsonDataReader`, usado só pelo branch intermediário de
   `pipeline.py` e pelos scripts de migração).
5. O branch `elif not force_extract and _raw_has_data(): ...` dentro de `run_medallion_pipeline`
   (`pipeline.py`), junto com as funções `_raw_has_data`/`_load_raw_data`. O pipeline passa a ter só
   dois caminhos: cache-hit na Bronze, ou extração real via `extract_and_land`.
6. As constantes `PROFILES_JSON`, `POSTS_JSON`, `REELS_JSON`, `ALL_XLSX`, `PROCESSED_DATA_DIR` em
   `config/settings.py` (órfãs após as remoções acima). `RAW_DATA_DIR` e `GOVERNADORES_FILE`
   permanecem -- ainda ativos.
7. `data/processed/` (pasta inteira, incluindo `all.xlsx` versionado e um arquivo `.pbix` pessoal
   não versionado que vivia na mesma pasta -- por decisão do usuário, esse arquivo permanece
   preservado apenas no backup local `data_backup_20260830_152309/` feito durante o teste da ADR
   0012, não no ambiente ativo).

`ModelEnricher` (`src/features/gold/model_enricher.py`) foi explicitamente excluído desta remoção --
apesar de também ser importado pelos scripts de migração legados, é um componente ativo, usado por
`lambdas/model/handler.py`, `src/modeling/clustering.py`, `src/modeling/orchestration.py` e
`scripts/run_profile_clustering_engagement.py`.

## Por que

**A migração já aconteceu; manter o caminho de migração depois de usado é código morto.** Os dois
scripts de `legacy/`/`scripts/migrate_to_medallion.py` resolviam um problema de transição
(Excel/JSON → Delta) que não existe mais -- a Bronze de produção já tem o dado. Continuar
mantendo-os testável e sincronizado com o resto do código é custo sem benefício correspondente.

**Nenhum teste cobria esse caminho.** Confirmado por grep: nenhum arquivo em `tests/` referencia
`_raw_has_data`, `_load_raw_data`, `JsonDataReader` ou `ExcelDataRepository`. A remoção não altera a
cobertura de teste existente (101 passed / 3 skipped antes e depois).

**O teste E2E real da ADR 0012 é a validação que faltava para remover com confiança.** Antes desta
sessão, ninguém tinha rodado o pipeline consolidado (ADR 0011) contra dado real -- havia um risco
implícito de que o branch legado ainda fosse necessário como rede de segurança. A execução real
confirmou que o caminho Bronze cache-hit / extração real via `extract_and_land` é suficiente sozinho.

## Opções consideradas

- **Manter `legacy/` como referência histórica indefinidamente** (a decisão original, documentada no
  próprio `legacy/README.md`) -- rejeitada agora: o valor de "referência histórica" não justifica o
  custo de manutenção (imports, duplicação de `migrate_to_medallion.py`, um branch a mais em
  `pipeline.py` para revisar a cada mudança) depois que a migração foi validada como definitivamente
  concluída pelo teste real da ADR 0012. O histórico continua disponível via `git log`/tags, sem
  precisar viver como código no branch principal.
- **Remover só os dados (`data/raw/*.json`, `data/processed/all.xlsx`) e manter o código legado** --
  rejeitada: deixaria `legacy/pipeline_legacy.py`/`migrate_to_medallion.py` quebrados (dependem
  desses arquivos) sem nenhum aviso, pior que remover os dois juntos.

## Consequências

- `pipeline.py` fica com dois caminhos de obtenção de dado (cache-hit na Bronze / extração real),
  não três.
- `data/processed/` deixa de existir como diretório do projeto; qualquer artefato pessoal que
  estivesse lá (ex: dashboards `.pbix`) precisa ser mantido fora do repositório pelo próprio usuário.
- Histórico do pipeline Excel pré-Medallion continua acessível via `git log`/tags anteriores a esta
  ADR, caso seja necessário consultar no futuro.
- Nenhuma mudança de comportamento para quem já usa `pipeline.py`/os scripts consolidados da ADR
  0011 -- a remoção é de código e dados que já não eram exercitados no fluxo ativo.
