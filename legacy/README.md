# Legacy artifacts

Esta pasta contém scripts e recursos legados relacionados ao pipeline Excel/`all.xlsx`.

## O que está aqui

- `pipeline_legacy.py` — pipeline antigo que gera `data/processed/all.xlsx` via `ExcelDataRepository`.
- `migrate_to_medallion.py` — utilitário de migração que tenta puxar dados modelados de `all.xlsx` para as tabelas Delta.

## Status

- O fluxo recomendado atualmente é o pipeline Delta principal em `pipeline.py`.
- Os scripts desta pasta são mantidos apenas para referência histórica e compatibilidade com dados legados.
- Não é necessário executar esses scripts para usar o dashboard atual.

## Uso

Se você precisar gerar ou inspecionar o Excel legado por algum motivo, execute estes scripts explicitamente a partir da raiz do projeto:

```bash
uv run python legacy/pipeline_legacy.py
uv run python legacy/migrate_to_medallion.py
```

Mas, novamente, para o fluxo ativo do projeto, prefira `pipeline.py` e os dashboards que consomem Delta.