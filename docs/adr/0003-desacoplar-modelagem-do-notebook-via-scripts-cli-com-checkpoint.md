---
status: accepted
---

# Desacoplar o disparo da modelagem do notebook via scripts CLI, com checkpoint de modelo persistido

## Contexto

O ADR [0001](0001-separar-modelagem-em-etapas-deterministicas-e-refinamento-manual.md) separou a modelagem em duas etapas de código (`run_deterministic_modeling` e `refine_topics_with_gemini`, em `src/modeling/`), mas ambas só podiam ser disparadas de dentro de `notebooks/03_modelagem_hibrida.ipynb` — a etapa determinística ganhou depois um segundo caminho via `pipeline.py --run-modeling`, mas o refinamento via Gemini continuou dependente do notebook. O objetivo agora é eliminar essa dependência por completo: o notebook deve virar puramente leitura da Gold para análise/visualização, sem disparar nenhuma etapa de escrita.

O obstáculo técnico real: o `topic_model` (BERTopic já ajustado) só existe na memória do processo que rodou `run_deterministic_modeling`. Sem persisti-lo, as duas etapas não podem virar duas invocações de processo separadas (ex.: dois scripts CLI, rodados em momentos diferentes) sem reprocessar o embedding inteiro (~14 min) a cada refinamento.

## Decisão

- **Dois scripts novos em `scripts/`**, seguindo o padrão já usado em `scripts/migrate_to_medallion.py` (um arquivo por responsabilidade, uma função, `if __name__ == "__main__":`):
  - `scripts/run_modeling.py` — lê Silver via `DeltaRepository`, chama `run_deterministic_modeling(df_reels, df_comments, ModelingConfig())`. Aceita `--run-id` opcional (`argparse`); sem flags para sobrescrever parâmetros de modelagem. Imprime o `run_id` ao final.
  - `scripts/refine_topics.py` — `argparse` com `--run-id` **obrigatório**, carrega o checkpoint correspondente e chama `refine_topics_with_gemini(...)`.
- **`run_deterministic_modeling` passa a persistir um checkpoint incondicionalmente** (não é uma flag opcional), em `data/model_checkpoints/<run_id>/`, além de escrever em Gold como já fazia:
  - `topic_model/` — via `BERTopic.save()`
  - `df_comments.parquet` — o `df_comments` provisório completo, na ordem exata em que o modelo foi ajustado (`docs` é derivado de `df_comments['text_demojized']` na hora de carregar, não persistido à parte, para não haver risco dos dois artefatos dessincronizarem)
  - `pca_model.joblib`, `cluster_model.joblib` — via `joblib` (já dependência transitiva de `scikit-learn`)
  - `metadata.json` — `cluster_config`, `cluster_score`, `cluster_algo_name`
- Isso vale para **qualquer chamador** de `run_deterministic_modeling` — notebook, `pipeline.py --run-modeling`, e os dois scripts novos — não é um comportamento exclusivo do caminho CLI.
- `notebooks/03_modelagem_hibrida.ipynb` deixa de chamar `run_deterministic_modeling`/`refine_topics_with_gemini`. Lê `governor_sentiment`/`governor_clusters` direto da Gold para os resultados finais, e lê o checkpoint persistido (`pca_model.joblib`, `cluster_model.joblib`, `metadata.json`) para as visualizações de PCA e validação de cluster que hoje vêm do objeto `result` em memória.
- Sem política de limpeza automática de checkpoints — `data/model_checkpoints/` cresce a cada rodada da etapa determinística, e a limpeza é manual por enquanto.

## Por que

O checkpoint existe só para viabilizar a etapa de refinamento rodar como uma invocação de processo separada, em qualquer momento, sem perder o resultado do estágio determinístico. A persistência é incondicional porque torná-la opcional reintroduziria o problema original: seria fácil esquecer de pedi-la numa rodada e ficar sem como refinar depois sem reprocessar tudo. `df_comments` é persistido inteiro (não só `docs`) porque reconstruir a partir de uma releitura do Gold arriscaria desalinhar `Topic`/`Name` silenciosamente — Delta não garante ordem de leitura igual à de escrita.

## Opções consideradas

- **Invocação única (determinístico + refinamento no mesmo processo, sem checkpoint)** — rejeitada: elimina o checkpoint de revisão humana entre as duas etapas, que é o motivo original da separação no ADR 0001.
- **Persistência do checkpoint opcional via flag** — rejeitada: reintroduz o risco de esquecer de habilitá-la numa rodada e não conseguir refinar depois sem reprocessar.
- **Reconstruir `docs`/`df_comments` relendo `governor_sentiment` no Gold em vez de persistir separadamente** — rejeitada: ordem de leitura do Delta não é garantida igual à de escrita; risco real de desalinhar `Topic`/`Name` entre linhas sem nenhum erro visível.
- **Um único script com subcomandos (`argparse` com `deterministic`/`refine`) em vez de dois arquivos** — rejeitada: quebraria o padrão de "um script por responsabilidade" já estabelecido em `scripts/migrate_to_medallion.py`.
- **Retenção automática de checkpoints (manter só os N mais recentes, ou apagar após o refinamento)** — rejeitada por ora: complexidade desnecessária para o volume de execuções de um projeto de TCC, não um sistema em produção.

## Consequências

- `data/model_checkpoints/` cresce a cada rodada da etapa determinística (cada checkpoint carrega os embeddings do corpus inteiro) — limpeza manual, sem lógica automática.
- `run_deterministic_modeling` ganha uma responsabilidade de I/O de sistema de arquivos além da escrita em Delta, mas a assinatura pública não muda.
- O notebook 03 deixa de ser o "centro de pesquisa" citado no README — vira puramente instrumentação e análise, lendo de Gold e do checkpoint, nunca escrevendo. `pipeline.py` e os scripts novos passam a ser os únicos disparadores de escrita da modelagem.
