---
status: accepted
---

# Coleta versionada no Hugging Face, Bronze fiel e AWS que só reconstrói

## Contexto

O projeto acumulou três camadas de armazenamento do dado bruto e dois destinos de nuvem, cada um decidido num momento
diferente:

- A **Bronze** (Delta, append-only, com `run_id`) descarta silenciosamente os campos que o esquema fixo não conhece
  ([ADR 0011](0011-preparar-medallion-para-monitor-continuo-landing-zone-extracao-unica-historico-gold.md)). A **landing**
  (`landing/<run_id>/*.json`) foi criada como remendo dessa perda e nunca é lida por ninguém.
- O histórico (`*_history`, `week_over_week`, "execução anterior") serve a um monitor contínuo que nunca existiu: 17
  arquivos citam `_history`, e o dashboard só consome `load_sentiment_history`.
- A AWS (ADRs 0007, 0008, 0009, 0016) foi desenhada para extração agendada. `terraform apply` **nunca foi aplicado**.
- O Hugging Face passou a distribuir os dados entre máquinas
  ([ADR 0035](0035-dados-coletados-distribuidos-por-dataset-privado-no-hugging-face.md)) e Silver e Gold para o app
  ([ADR 0036](0036-dashboard-no-streamlit-cloud-com-silver-e-gold-baixados-do-hugging-face.md)), com regras de escritor
  único e de divergência.

A necessidade real, dita pelo autor: extrair um período (hoje 3 meses, depois 12), manter **todas as extrações salvas e
versionadas**, e a mais recente sempre vigente. Usar o Hugging Face como camada comum à execução local e à nuvem.

A pesquisa na documentação do Databricks e da Microsoft (Fabric) mostrou que a Bronze deve guardar o dado **como chegou**
(no formato original ou convertido para Delta), com metadados de ingestão, e que parsing e validação pertencem à Silver. A
landing zone é uma camada extra opcional, não uma das três.

## Decisão

1. **Coleta** é o conceito central: uma extração segundo um **Recorte** (janela relativa, intervalo absoluto, teto por
   perfil, ou combinação). Termos em `CONTEXT.md`.
2. **Snapshot** = Coleta vigente + Bronze, Silver e Gold derivadas + manifesto, num único commit do dataset do Hugging Face.
3. **Bronze fiel.** Cada registro guarda o item completo da Apify numa coluna bruta, além dos campos tipados e dos metadados
   de ingestão. Nada é descartado. Grava em overwrite por Coleta, sem `run_id` acumulado. **A landing deixa de existir.**
   Parsing e validação ficam na Silver.
4. **Uma Coleta substitui a outra.** A `main` do dataset guarda só a Coleta vigente (commit de substituição). As anteriores
   ficam salvas por **tag** e nunca são apagadas nem reescritas (sem force-push). Restaurar = baixar a tag e publicar como
   novo commit.
5. **Tag** gerada a partir do Recorte: `coleta_<extração>[_<janela>][_<teto>][_<rótulo>]` (gramática em
   `docs/agents/coletas.md`). A verdade fica no **manifesto**: identidade, Recorte pedido, cobertura real por fonte e perfil,
   custo, tabelas derivadas com linhas. O manifesto não carrega conteúdo nem segredos.
6. **O dashboard publicado baixa a `main`**; `HF_DATASET_REVISAO` (tag ou commit) mostra uma Coleta antiga.
7. **Sem histórico entre execuções.** Saem as tabelas `*_history` sem chamador e o "vs. execução anterior" do dashboard.
   A comparação temporal passa a vir de dentro de uma Coleta (datas das publicações), não de Coletas distintas.
8. **AWS sem agendamento e sem extração.** A nuvem baixa uma tag do HF e reconstrói Bronze, Silver e Gold no S3 (etapas
   determinísticas). Extração (Apify) e modelagem pesada (BERTopic, ~14 min só de embedding, ~2,5 GB de modelos) continuam
   locais, porque não cabem nos 15 min da Lambda. Como o `terraform apply` nunca foi aplicado, não há o que desmontar.
9. **Módulo Coleta único** substitui os modos do `pipeline.py` e os scripts `run_apify_backfill`, `calibration` e
   `mentions_pilot`.

## Alternativas consideradas

- **Landing no HF, Bronze reconstruída:** mantém a camada bruta fora do vocabulário Medallion e uma etapa landing→Bronze
  só para compensar uma Bronze infiel.
- **Landing como Bronze, sem Delta:** obriga a Silver a ler JSON e deixa a camada com um nome pouco informativo.
- **Todas as Coletas em pastas lado a lado com ponteiro `CURRENT`:** o dataset cresce a cada Coleta e todo download lê o
  ponteiro; as tags já dão o acesso a cada uma.
- **Derivadas fora do commit da Coleta:** Coleta e derivadas podem sair de sincronia.

## Consequências

- **Supera** a ADR 0016 por inteiro e **em parte** as ADRs 0007, 0008, 0009 (agendamento e extração na AWS), 0011
  (landing, extração consolidada nos três modos, histórico em Gold) e 0035 (Bronze deixa de ser a única fonte sincronizada
  e as regras de escritor único e divergência dão lugar a commit de substituição + tag) e 0036 (o app continua
  baixando só Silver e Gold, agora de uma revisão escolhida).
- Re-extrair uma janela maior repaga o período sobreposto na Apify: uma Coleta substitui a outra, não a complementa.
- O histórico do dataset ocupa armazenamento; conferir o limite da conta privada do HF.
- Fica anotado como risco: confirmar se o actor da Apify aceita data final; se não, o intervalo absoluto será obtido
  extraindo desde o início e recortando localmente.
- A Coleta piloto de 2026-10-06 será marcada com tag antes de ser substituída; como a Bronze atual descartou campos,
  o piloto não terá a coluna bruta completa (a landing dele no HF a contém).
