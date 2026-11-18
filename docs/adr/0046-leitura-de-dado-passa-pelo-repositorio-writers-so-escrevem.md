---
status: accepted
---

# Leitura de dado passa pelo repositório; writers só escrevem

## Contexto

Até aqui o `BronzeWriter` lia além de escrever: expunha `get_latest_*`, `get_profiles_at` e `get_history`, e era por
eles que a derivação Silver/Gold (`derivar_silver_gold`) lia a Bronze. A reconstrução da Lambda levava isso ao
extremo: construía um `BronzeWriter` apontando para o Snapshot só para ler, e nunca escrevia por ele.

Consequências práticas:

- Duas classes (`BronzeWriter` e `DeltaRepository`) sabiam abrir tabelas Delta com `storage_options` e fazer time
  travel. Quando o deltalake 1.x passou a fazer `load_as_version` no lugar (devolvendo `None`), o time travel quebrou
  nas duas, e só o repositório ganhou teste e correção (issue #313).
- O `DeltaRepository` não cobria a Bronze (não tinha `bronze_dir`) nem toda a Silver, então os notebooks de
  diagnóstico liam a Bronze pela classe de escrita e algumas Silver com `DeltaTable` direto, contrariando a frase do
  README de que o repositório é a única porta de leitura.
- Não havia regra escrita sobre quem pode ler o quê; cada novo consumidor decidia sozinho.

A issue #313 deu ao repositório os acessores que faltavam (`load_bronze_*`, `load_silver_*`). Esta ADR fecha o outro
lado: tira a leitura do writer e registra a regra.

## Decisão

1. **Dado de tabela (um DataFrame de Bronze, Silver ou Gold) é lido só pelo `DeltaRepository`.** Vale para
   dashboards, notebooks, scripts e para a própria derivação Silver/Gold, local ou na Lambda.
2. **Writers só escrevem.** `BronzeWriter` perde `get_latest_*`, `get_profiles_at`, `get_history` e os auxiliares de
   leitura. Os writers de Silver e Gold já eram só escrita.
3. **`derivar_silver_gold` recebe um `DeltaRepository`** (com `bronze_dir`) para ler e continua recebendo os caminhos
   de destino para escrever. Leitura e escrita podem apontar para lugares diferentes: a reconstrução lê o Snapshot
   local e grava no S3. `repositorio_do_destino(caminhos_do_destino(...))` é o atalho que `coletar()` e
   `reconstruir()` usam.
4. **Exceções nomeadas: metadados de tabela podem usar `DeltaTable` direto.** Contagem de linhas e último commit
   (`manifesto.py`, `pipeline_report.py`), cópia de uma tabela entre storages preservando schema
   (`reconstruir._copiar_tabela`) e a varredura de `_run_id` de `scripts/inspect_runs.py` não são leitura de dado de
   negócio; forçá-las no repositório só engordaria a interface. O read-modify-write interno de
   `ModelEnricher.write_sentiment` (relê a própria tabela de destino para preservar outras `fonte`s antes de
   sobrescrever) é parte da escrita, não leitura de consumidor.
5. **Nomes dizem a camada.** Acessores novos do repositório levam a camada no nome (`load_bronze_*`,
   `load_silver_*`). Os antigos sem prefixo (`load_profiles`, `load_comments`, `load_ugc_mentions`) continuam porque
   o dashboard depende deles, com docstring dizendo o que leem.

## Alternativas rejeitadas

- **Manter o writer lendo e só adicionar os acessores ao repositório:** deixa duas implementações de "abrir Delta"
  e o nome `Writer` mentindo; foi o que permitiu o time travel quebrar sem ninguém notar.
- **Criar um `BronzeReader` separado:** terceira classe para o mesmo primitivo que o `DeltaRepository` já tem.
- **Levar também os metadados (contagem, histórico, cópia) para o repositório:** cresce a interface para servir
  utilitários de operação que precisam do `DeltaTable` cru, não de DataFrames tipados.

## Consequências

- A assinatura de `derivar_silver_gold` muda (`repo` no lugar de `bronze`); os dois únicos chamadores
  (`coletar.py`, `reconstruir.py`) mudam junto.
- Testes de round-trip (`test_bronze_writer.py`, `test_post_comments.py`) escrevem pelo writer e leem pelo
  repositório, no layout padrão `bronze/<tabela>`. `get_table_history` do repositório ganha `layer`.
- A derivação ganha um teste próprio, ponta a ponta em diretório temporário (`test_coleta_derivacao.py`), além da
  cobertura indireta por `test_coleta_coletar.py` e `test_rebuild_lambda.py`.
- ADRs anteriores que citam `BronzeWriter.get_latest_*` (0012, 0022) ficam como registro histórico.
