## Agent skills

### Issue tracker

Issues vivem no GitHub Issues deste repo (via `gh` CLI); PRs externas não entram na fila de triagem. See `docs/agents/issue-tracker.md`.

### Triage labels

Vocabulário padrão (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix), sem mapeamento — repo não tinha labels de triagem pré-existentes. See `docs/agents/triage-labels.md`.

### Domain docs

Contexto único — `CONTEXT.md` na raiz + `docs/adr/`. See `docs/agents/domain.md`.

### Coletas

Extrações do Instagram são versionadas no Hugging Face com tags `coleta_<extração>[_<janela>][_<teto>][_<rótulo>]`; nunca extrair sem `--yes` e aval explícito, nunca apagar uma Coleta anterior. See `docs/agents/coletas.md`.
