---
license: mit
language:
  - pt
pretty_name: Governadores no Instagram (Medallion)
tags:
  - instagram
  - nlp
  - governadores
  - medallion
---

# Governadores no Instagram, camadas Medallion

Dados do Instagram dos governadores dos estados brasileiros, coletados via Apify e organizados nas camadas **Bronze, Silver e Gold**. Alimentam o dashboard de growth e os notebooks do projeto [Técnicas de Ciência de Dados em dados do Instagram](https://github.com/Vini0606/Tecnicas-de-Ciencia-de-Dados-em-dados-do-Instagram).

> **Dataset privado.** Há dados pessoais de terceiros (comentários, usuários que marcam os governadores). Não redistribua.

## Coleta vigente

A `main` guarda **só a Coleta vigente**. Cada Coleta é um commit, identificado pela mensagem `push: coleta_...` e descrito pelo `manifesto.json`, que é a fonte de verdade sobre o que foi extraído.

| | |
|---|---|
| **Identificador** | `coleta_2026-10-06_ultimos-5d_teto-30` (mensagem do commit `ceba2982`) |
| **Extração** | 2026-10-06, a partir das 17:27 UTC |
| **Recorte** | últimos 5 dias, teto de 30 itens por perfil |
| **Perfis** | 26 governadores |
| **Tags de uso** | `reboot-iesb`, a Coleta apresentada no evento da IESB |

**Como o Recorte foi determinado.** Esta Coleta foi extraída antes de o manifesto existir. O Recorte foi inferido dos próprios dados: todo item anterior à janela é um post fixado (a Apify devolve itens fixados fora da data pedida) e nenhum perfil passa de 30 itens, com 12 perfis nos 30 exatos em posts e 7 em reels.

### Cobertura

| Fonte | Itens (Bronze) | Datas |
|---|---|---|
| Posts | 601 | 2026-05-05 a 2026-10-06 (os mais antigos são fixados) |
| Reels | 522 | 2025-01-06 a 2026-10-06 (os mais antigos são fixados) |
| Perfis | 26 | dados de perfil no momento da extração |
| UGC (posts de terceiros que marcam o governador) | 246 | 233 deles nos últimos 5 dias |

Linha do tempo (UTC): perfis às 17:27, posts às 17:29, reels às 18:37 e UGC às 18:38 de 2026-10-06. A Silver e a Gold foram derivadas em 2026-10-07, a partir da mesma Bronze.

## Estrutura

```
bronze/   dado da Apify, uma tabela Delta por fonte
silver/   dado limpo e conformado
gold/     métricas e modelagem consumidas pelo dashboard
landing/  payload bruto da extração (só nesta Coleta; Coletas novas não têm landing)
manifesto.json
```

- **Bronze:** `instagram_posts`, `instagram_profiles`, `instagram_reels`, `ugc_mentions`. Nesta Coleta a Bronze **não tem a coluna `_raw`** com o item completo da Apify; o payload completo está em `landing/`. Coletas novas guardam o item completo na Bronze.
- **Silver:** posts, reels, perfis, comentários de reels e de posts, UGC e metadados dos governadores.
- **Gold:** engajamento, NSM, scorecard, clusters de posts e reels, sentimento, tópicos de discurso, prioridade de pautas, menções UGC e a regressão de performance por post.
- **Tabelas legadas desta Coleta:** `governor_nsm_history` e `governor_sentiment_history` existem aqui, mas o código atual não gera mais `governor_nsm_history`, e nenhuma tela as lê.

O manifesto traz a identidade da Coleta, o Recorte, a cobertura por fonte e por perfil e a contagem de linhas de cada tabela. Para esta Coleta, o custo na Apify não foi registrado.

## Como usar

- **Dashboard:** baixa `silver/`, `gold/` e `manifesto.json` da `main`. Para mostrar outra Coleta, defina `HF_DATASET_REVISAO` com uma tag de uso ou o hash do commit.
- **Reconstruir as camadas:** a partir de uma Coleta (identificador, tag de uso ou hash de commit), a Lambda `rebuild` (AWS) regenera Bronze, Silver e Gold no S3.
- **Baixar uma Coleta:** `coleta.py baixar <coleta> --destino <pasta>` (identificador, tag de uso ou hash de commit); listar: `coleta.py listar`.

## Convenção de commits e tags

- **Cada Coleta é um commit na `main`.** A mensagem segue o estilo do Git, com o identificador da Coleta na descrição: `push: <identificador>` ao publicar e `restore: <identificador>_restaurada` ao restaurar.
- **Identificador:** `coleta_<data da extração>[_ultimos-Nd | _de-AAAA-MM-DD_ate-AAAA-MM-DD][_teto-N][_rotulo]`. Não é uma tag; fica na mensagem do commit e no manifesto.
- **Tags são só de uso**, criadas à mão (ex.: `reboot-iesb`, `tcc`, `article-governor-segmentation`). Apontam para o commit de uma Coleta e nunca são movidas nem apagadas pelo projeto. Se a `main` for reescrita (squash), só sobrevivem as Coletas que tiverem uma tag.
- **Restaurar uma Coleta antiga na `main`:** novo commit; nunca force-push.

Convenção completa: `docs/agents/coletas.md` e ADR 0039 no repositório do projeto.
