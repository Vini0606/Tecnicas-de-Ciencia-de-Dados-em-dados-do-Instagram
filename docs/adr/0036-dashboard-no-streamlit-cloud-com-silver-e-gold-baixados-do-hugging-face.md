---
status: accepted
---

# Dashboard no Streamlit Cloud, com Silver e Gold baixados de um dataset privado do Hugging Face

## Contexto

O dashboard lê `data/silver` e `data/gold` (17 tabelas Gold e 5 Silver, cerca de 3 MB). Esses diretórios não vão
para o git. No primeiro deploy no Streamlit Community Cloud o app subiu, mas vazio: o clone não traz `data/` e as
telas mostravam "rode a pipeline". A ADR [0035](0035-dados-coletados-distribuidos-por-dataset-privado-no-hugging-face.md)
leva só `landing/` e `bronze/` entre máquinas e diz que Silver e Gold nunca sobem, porque se regeneram com
`pipeline.py --run-modeling` (15 a 30 minutos e cerca de 2,5 GB de modelos), o que não cabe num app de visualização.

O deploy também instalava 165 pacotes, incluindo `bertopic` e o PyTorch com CUDA, porque `dashboard/screens/produzir.py`
importava `DEGENERATE_TOPIC_LABEL` de `src/modeling/gemini_refiner.py`, que importa bertopic, scipy e o SDK do Gemini.

## Decisão

1. **Publicar Silver e Gold em um dataset privado do HF, separado do dataset da landing/Bronze.** Um segundo
   dataset (`HF_DATASET_REPO_PUBLICACAO`) recebe só `silver/**` e `gold/**`. O token do app é de leitura e vale só
   para esse dataset, então nunca alcança o dado bruto pago e insubstituível. Isso **revisa a ADR 0035** apenas no
   ponto "Silver e Gold não sobem": eles sobem, mas para outro dataset e só para alimentar o dashboard.
2. **Baixar na inicialização.** `dashboard/core/bootstrap_dados.py` roda no topo de `dashboard/app.py`, uma vez
   por processo (`st.cache_resource`). Se `data/gold/governor_engagement` já existe (uso local), não faz nada. Se
   não existe e `HF_TOKEN` e `HF_DATASET_REPO_PUBLICACAO` estão nos Secrets (ou no `.env`), baixa Silver e Gold com
   `snapshot_download`. Sem configuração, o comportamento antigo se mantém (aviso de dados ausentes). Falha de rede
   ou de permissão vira uma mensagem de erro na tela, sem derrubar o app e sem o token.
3. **Publicar do computador de quem rodou a pipeline:** `scripts/publicar_dashboard_hf.py` mostra o plano e só
   envia com `--yes`. Recusa publicar sem nenhuma tabela Gold.
4. **Dependências enxutas.** `DEGENERATE_TOPIC_LABEL` foi para `src/modeling/topic_labels.py` (sem NLP), e
   `gemini_refiner` continua exportando o nome. O dashboard não importa mais bertopic, scipy, torch nem o SDK do
   Gemini (um teste confere). `dashboard/requirements.txt` lista só o que o dashboard usa; o Streamlit Cloud
   procura o arquivo de dependências na pasta do entrypoint (`dashboard/app.py`) antes da raiz.

## Consequências

- **O app é uma foto.** Para atualizar, rode a pipeline, publique e reinicie o app (o disco do Streamlit Cloud é
  efêmero e o download roda de novo a cada reinício). A publicação envia os arquivos de cada tabela Delta, e não
  remove tabelas apagadas do dataset.
- **Dado pessoal de terceiros.** O Gold inclui textos de comentários e métricas de UGC de terceiros. O dataset é
  privado, mas o app deve ser restrito a visualizadores autorizados no Streamlit Cloud (Share), e não público.
- **Credenciais:** `HF_TOKEN` (leitura) e `HF_DATASET_REPO_PUBLICACAO` nos Secrets do app. Para publicar, o token
  do `.env` precisa de escrita nesse dataset.
- Ponto em aberto: a escolha de onde hospedar (Streamlit Cloud, container com S3) continua podendo mudar. O
  `DeltaRepository` já aceita `s3://`, mas o dashboard ainda não passa `storage_options`.
