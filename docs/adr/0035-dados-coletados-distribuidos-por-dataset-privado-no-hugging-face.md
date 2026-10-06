---
status: accepted
---

# Dados coletados distribuídos por um dataset privado no Hugging Face

## Contexto

A coleta na Apify é paga e acontece numa máquina (o notebook). A modelagem, pesada em CPU, precisa rodar
em outra (o desktop). Hoje os dados vivem só em `data/`, que está no `.gitignore`
([ADR 0013](0013-remover-pipeline-legado-excel-e-artefatos-de-migracao-ja-concluida.md)), e não havia
forma suportada de levá-los de uma máquina para outra:

- **Recoletar em cada máquina** custa de novo e traz dados diferentes, porque o Instagram muda entre
  coletas.
- **O repositório é público.** A landing e a Bronze trazem `ownerUsername` e textos de comentaristas e de
  autores de UGC, que são cidadãos comuns. Commitar ou publicar abertamente divulgaria dado pessoal de
  terceiros (LGPD).
- **O bucket S3 do Terraform** ([ADR 0007](0007-generalizar-deltarepository-para-s3-e-aposentar-is-cloud.md),
  [ADR 0008](0008-orquestrar-lambdas-via-orquestradora-unica-e-terraform.md)) nunca foi aplicado a partir
  da máquina de trabalho: não há state, credenciais nem `S3_BUCKET` preenchido.
- **O `pipeline.py` lê a Bronze, não a landing.** Não existe carregador landing → Bronze.

Decidido em sessão de grilling com o usuário em 2026-10-06 (spec #231).

## Decisão

1. **Fonte durável e privada:** um **dataset privado no Hugging Face** (`repo_type="dataset"`),
   identificado por `HF_DATASET_REPO` e acessado com `HF_TOKEN` (token fine-grained, com escrita só nesse
   dataset, um por máquina). O cliente é a biblioteca `huggingface_hub`.
2. **Escopo: landing + Bronze**, espelhando `data/landing/` e `data/bronze/` 1:1, incluindo os
   `_delta_log`. A landing é o bruto já pago e insubstituível. A Bronze é o que o `pipeline.py` lê. Silver,
   Gold, checkpoints e logs **não** sobem: são regeneráveis a custo zero com
   `pipeline.py --run-modeling`, e versioná-los confundiria qual é a fonte da verdade.
3. **Movimentação explícita, fora do `pipeline.py`:** um script dedicado
   (`scripts/sync_dados_hf.py push|pull`, issue #232). Enviar dado para fora é sempre deliberado
   (`push --yes`), no mesmo espírito do `--yes` que confirma custo na Apify.
4. **Escritor único.** A landing não conflita, porque cada execução é uma pasta `<run_id>/` nova. A Bronze
   é Delta só de acréscimos, e duas máquinas extraindo divergem o `_delta_log`. Regra: **só uma máquina
   coleta por vez**.
   - O `push` recusa se a Bronze remota estiver à frente ou divergente; nesse caso, `pull` antes.
   - O `pull` recusa sobrescrever landing ou Bronze locais ainda não enviadas, com `--force` como saída
     consciente.
5. **Versionamento:** cada envio é um commit no dataset, com os `run_id` na mensagem. Uma versão antiga é
   recuperável pela revisão do HF.

## Alternativas descartadas

- **Commitar `data/landing` no repositório:** o repo é público (dado pessoal de terceiros), o histórico
  do git cresceria a cada coleta (37 MB na primeira) e contraria a ADR 0013.
- **Dataset público no HF:** mesmo problema de dado pessoal.
- **Anonimizar e publicar:** é um projeto em si e mexe no contrato da Bronze. Fica para quando houver
  necessidade real de publicação (por exemplo, para a banca do TCC).
- **S3 agora:** exige conta AWS, `terraform apply`, credenciais e custo mensal para resolver uma
  transferência entre duas máquinas. Volta a fazer sentido quando o caminho serverless for ativado de
  verdade, e aí o S3 pode substituir o HF como fonte.
- **Repo GitHub privado só de dados:** o git não foi feito para binário crescente (Delta e JSONs grandes).
- **Drive/OneDrive:** manual, sem versão por execução e sem download por código.

## Consequências

- Uma máquina nova sobe o dashboard sem pagar coleta: baixa landing + Bronze do HF e roda
  `pipeline.py --run-modeling`.
- O dado continua privado: o acesso depende de um token pessoal, nunca versionado (`.env`).
- **Primeira carga (2026-10-06):** feita manualmente com `huggingface_hub.upload_folder` no mesmo layout
  espelho, com 12 arquivos e 42,9 MB (landing da execução `20261006_172720_a925d361` + 4 tabelas Bronze).
  A integridade foi conferida por download e hash, e as tabelas Delta baixadas abriram normalmente. O
  script da #232 passa a gerenciar esse mesmo dataset, sem retrabalho.
- **Evolução:** se mais de uma máquina passar a coletar, o caminho é tratar a landing como fonte única e
  reconstruir a Bronze localmente a partir dela (carregador landing → Bronze, hoje inexistente), eliminando
  o conflito de `_delta_log` por construção.
- O script `scripts/sync_dados_hf.py push|pull` (issue #232) substitui os comandos avulsos do `huggingface_hub`.
