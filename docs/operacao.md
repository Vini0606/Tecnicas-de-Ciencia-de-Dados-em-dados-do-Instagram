# Operação: fluxos alternativos e manutenção

Receitas que o fluxo principal do [README](../README.md#6-como-executar) não cobre. Cada uma roda isolada, sem reprocessar os estágios anteriores. Os termos (**Coleta**, **Recorte**, **Snapshot**) estão definidos em [`CONTEXT.md`](../CONTEXT.md).

## Sumário

- [Só re-rodar a modelagem](#só-re-rodar-a-modelagem-bronzesilvergold-engagement-já-existem)
- [Refinar rótulos de tópico via Gemini](#refinar-rótulos-de-tópico-via-gemini-etapa-manual-revisão-humana)
- [Métricas pós-modelagem independentes](#métricas-pós-modelagem-independentes-adr-0020)
- [UGC de menções](#ugc-de-menções-adr-0020-ficha-8--issue-93)
- [Publicar o dashboard no Streamlit Cloud](#publicar-o-dashboard-no-streamlit-cloud-dados-do-hugging-face)
- [Levar os dados coletados para outra máquina](#levar-os-dados-coletados-para-outra-máquina-dataset-privado-no-hugging-face)
- [Reconstruir na nuvem a partir de uma Coleta (AWS)](#reconstruir-na-nuvem-a-partir-de-uma-coleta-aws)
- [Inspecionar `run_id`s](#inspecionar-run_ids-espalhados-pelo-projeto)

---

## Só re-rodar a modelagem (Bronze/Silver/Gold-engagement já existem)

Útil para repetir a modelagem sobre uma Coleta específica (`--parent-run-id`) sem reprocessar Silver/Gold-engagement:

```bash
uv run python scripts/run_modeling.py --parent-run-id <RUN_ID_DA_COLETA>
```

`--parent-run-id` é obrigatório — é o `run_id` da Coleta que gerou a Silver sendo usada aqui, gravado no checkpoint só para rastreabilidade (dados → modelo, ver `scripts/inspect_runs.py --pipeline`); nunca substitui o `run_id` próprio que a modelagem sempre cunha ([ADR 0001](adr/0001-separar-modelagem-em-etapas-deterministicas-e-refinamento-manual.md)).

`run_modeling.py` imprime o `run_id` usado — é esse valor que vai em `--run-id` do `refine_topics.py` (e em `RUN_ID` no notebook 03). Cada chamada de `run_deterministic_modeling` grava incondicionalmente um checkpoint local em `data/model_checkpoints/<run_id>/` — o `topic_model` do BERTopic, o `df_comments`/`df_reels` provisórios e os modelos de PCA/clustering — porque sem isso o refinamento via Gemini só poderia rodar no mesmo processo que acabou de ajustar o `topic_model` ([ADR 0003](adr/0003-desacoplar-modelagem-do-notebook-via-scripts-cli-com-checkpoint.md)).

## Refinar rótulos de tópico via Gemini (etapa manual, revisão humana)

Nunca roda sozinho dentro da CLI da Coleta (decisão da [ADR 0001](adr/0001-separar-modelagem-em-etapas-deterministicas-e-refinamento-manual.md)) — só depois de inspecionar os tópicos provisórios em `governor_sentiment`/`governor_discourse_topics`:

```bash
# preencher API_GEMINI no .env antes
uv run python scripts/refine_topics.py --run-id <RUN_ID_DO_CHECKPOINT_DE_MODELAGEM>
# opcional: --target comments | discourse (padrao: all = comentarios + discurso)
```

Por padrão o script refina os tópicos de comentário (`governor_sentiment`, preservando as linhas de legenda/transcrição, e o Score ICE) **e** os tópicos de discurso (`governor_discourse_topics`, assunto das legendas). O ruído (`-1`) não é refinado e o tópico degenerado (sem palavra alguma) recebe o rótulo "sem assunto definido". Checkpoints gravados antes da issue #186 não têm o modelo de discurso: com `--target discourse` o script falha com mensagem clara; com o padrão, pula o discurso.

**Procedimento e ordem relativa ao ICE de pautas.** (1) Rode `run_modeling.py` (ou `coleta.py coletar --modelar`) e anote o `run_id`: ele grava o checkpoint (incluindo o modelo de discurso) e um `content_topic_priority_score` *provisório*, com rótulos brutos. (2) Confira os tópicos provisórios em `governor_sentiment`/`governor_discourse_topics` (etapa de revisão humana). (3) Rode o refino com `--target all` (comentários primeiro, depois discurso) ou `--target discourse`; o ICE de pautas (`content_topic_priority_score`) é **recalculado dentro do refino de discurso**, a partir dos comentários do checkpoint (já refinados no `all`), então não há comando separado e **não** se roda o ICE antes do refino. (4) `--target comments` sozinho não toca `governor_discourse_topics` nem o ICE de pautas. O refino de discurso nunca mexe nas linhas de legenda/transcrição de `governor_sentiment`. O refino **não** grava nas tabelas `_history`: ele só reescreve `Topic`/`Name`, sem gerar uma nova medição de sentimento.

## Métricas pós-modelagem independentes (ADR 0020)

Rodam sobre tabelas Gold já existentes, sem depender uma da outra nem do restante da modelagem:

```bash
uv run python scripts/run_growth_metrics.py                  # CMGR + retenção de sentimento -> governor_growth_metrics (Ficha 7)
uv run python scripts/run_governor_scorecard.py               # Escore composto dos governadores -> governor_scorecard (ADR 0030; também roda em --modelar)
```

`governor_nsm`, `topic_priority_score`, `governor_discourse_topics` e `governor_profile_clusters_engagement` já saem de `coleta.py coletar --modelar` / `scripts/run_modeling.py` — não precisam de script separado. `scripts/run_profile_clustering_engagement.py` continua existindo só para re-rodar esse estágio isolado (ex.: depois de um ajuste que só afeta a clusterização de perfil), sem repetir toda a modelagem determinística.

`governor_growth_metrics` (CMGR de audiência e retenção de sentimento positivo) segue gerada, mas hoje sem consumidor no dashboard (`dashboard/core/data.py::load_growth_metrics()` permanece disponível). `governor_scorecard` e `content_topic_priority_score` são lidas pela sub-aba Scorecard e pela fila de pautas de "O que produzir", respectivamente.

## UGC de menções (ADR 0020, Ficha 8 / issue #93)

O UGC (posts de terceiros que marcam ou mencionam o governador, `apify/instagram-tagged-scraper`) é coletado em toda Coleta, como última etapa tolerante a falha da extração ([ADR 0034](adr/0034-pipeline-ponto-unico-ugc-no-extrator-comentarios-de-posts-janela-e-relatorio.md)). Não há script isolado de coleta de UGC. O actor de UGC não filtra por data, então o teto (`--teto`) se aplica a ele mesmo numa Coleta por janela ([ADR 0044](adr/0044-teto-so-do-ugc-porque-o-actor-nao-filtra-por-data.md)).

## Publicar o dashboard no Streamlit Cloud (dados do Hugging Face)

O dashboard lê `data/silver` e `data/gold`, que não vão para o git. Em um deploy, esses diretórios (e o `manifesto.json`) são baixados do **dataset privado do Hugging Face** onde as Coletas são publicadas ([ADR 0036](adr/0036-dashboard-no-streamlit-cloud-com-silver-e-gold-baixados-do-hugging-face.md), [ADR 0039](adr/0039-coleta-versionada-no-hf-bronze-fiel-e-aws-so-reconstroi.md)).

1. **Publicar** (de quem rodou a Coleta), com `HF_TOKEN` (escrita) e `HF_DATASET_REPO` no `.env`: `coleta.py publicar <pasta>` (mostra o plano) e depois `... --yes` (envia).
2. **No Streamlit Cloud:** entrypoint `dashboard/app.py`; em *Settings > Secrets* adicione
   `HF_TOKEN = "<token>"`, `HF_DATASET_REPO = "<usuario>/<nome>"` e
   `APP_PASSWORD = "<senha longa>"` (o app pede essa senha; sem ela, fora do `localhost`, ele fica
   **bloqueado**, [ADR 0037](adr/0037-dashboard-exige-senha-no-proprio-app.md)). Em *Share*, restrinja os visualizadores (há
   comentários de terceiros nos dados). Depois, *Reboot*.
3. **Trocar de Coleta:** publique a nova (vira a `main`) e reinicie o app. Para mostrar uma Coleta antiga sem mexer na `main`,
   defina `HF_DATASET_REVISAO = "<tag ou commit>"` nos Secrets.

Opcional e mais seguro: um dataset só do dashboard (`HF_DATASET_REPO_PUBLICACAO`) com um token só de leitura nos
Secrets, para o app nunca alcançar a Bronze.

O deploy instala só `dashboard/requirements.txt` (sem bertopic nem PyTorch).

**Reinicie o app (*Manage app > Reboot app*) depois de mesclar PRs que mexem em `src/` ou `dashboard/`, principalmente vários em sequência.**
O Streamlit Cloud atualiza os arquivos sem reiniciar o processo, e um módulo antigo que ficou em memória quebra o import de um arquivo novo
(já aconteceu: `ImportError: cannot import name 'ler_manifesto' from 'src.publicacao_hf'`, resolvido com o reboot).

## Levar os dados coletados para outra máquina (dataset privado no Hugging Face)

A coleta é paga, e o repositório é público, com dado pessoal de terceiros na Bronze. Por isso, os dados **não** vão para o git: ficam no
**dataset privado no Hugging Face**, versionados por Coleta ([ADR 0039](adr/0039-coleta-versionada-no-hf-bronze-fiel-e-aws-so-reconstroi.md), que superou parte da [ADR 0035](adr/0035-dados-coletados-distribuidos-por-dataset-privado-no-hugging-face.md)).

1. **Uma vez por máquina:** crie no Hugging Face um token **fine-grained** com acesso só ao dataset (escrita na máquina que publica, leitura basta nas demais) e preencha `HF_TOKEN` e `HF_DATASET_REPO` no `.env`.
2. **Na máquina que coletou:** `uv run python coleta.py publicar <pasta>` mostra o plano; com `--yes`, envia o Snapshot num único commit.
3. **Na outra máquina:** `listar` e `baixar`, e depois, se quiser, `coleta.py restaurar <coleta>` para trazer uma Coleta antiga de volta à `main`:

```bash
uv run python coleta.py listar
uv run python coleta.py baixar <coleta> --destino data
uv run python coleta.py restaurar <coleta> --yes    # opcional: volta a ser a Coleta vigente (novo commit)
```

`publicar` e `restaurar` recusam identificador já publicado e passar do limite de armazenamento (`--limite-bytes`); nunca apagam o commit de uma Coleta anterior. O Snapshot é landing + Bronze + Silver + Gold + manifesto ([ADR 0045](adr/0045-landing-volta-como-payload-bruto-completo-de-toda-coleta.md)); checkpoints de modelagem e logs não sobem. `baixar` traz a landing por padrão; `--sem-landing` a pula.

## Reconstruir na nuvem a partir de uma Coleta (AWS)

Depois de aplicar o Terraform e publicar a imagem (ver [`infra/README.md`](../infra/README.md)), a reconstrução é manual:

```bash
aws lambda invoke --function-name <nome-da-lambda-rebuild> --payload '{"tag": "<coleta>"}' --cli-binary-format raw-in-base64-out saida.json
```

Evento: `{"tag": "coleta_...", "run_id": "opcional"}` (`tag` aceita identificador, tag de uso ou hash de commit). `S3_BASE_PREFIX` (opcional) define um prefixo dentro do bucket. Publicar a imagem no ECR **não** atualiza a Lambda em execução — promover é manual:

```bash
TF_VAR_image_tag=$(git rev-parse origin/main) terraform apply
```

> No PowerShell (Windows): `$env:TF_VAR_image_tag = git rev-parse origin/main; terraform apply`

## Inspecionar `run_id`s espalhados pelo projeto

Consolida `data/logs/`, `data/model_checkpoints/` e as colunas `_run_id` da Bronze/Silver/Gold numa visão única (o script ainda procura as pastas legadas `data/backfill/`, que a Coleta não cria mais):

```bash
uv run python scripts/inspect_runs.py                    # lista todos os run_id conhecidos
uv run python scripts/inspect_runs.py --run-id <ID>       # detalhe de um run_id específico
uv run python scripts/inspect_runs.py --pipeline <ID>     # Coleta <ID> + toda modelagem que ela disparou
```
