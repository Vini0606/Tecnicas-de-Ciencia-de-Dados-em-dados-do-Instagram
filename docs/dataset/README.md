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

O manifesto (esquema v4) traz a identidade da Coleta, o Recorte pedido e a janela efetiva em datas, a cobertura por fonte e por perfil, o custo e a contagem de linhas de cada tabela. Nenhum campo é nulo: o que não se aplica simplesmente não aparece. Na cobertura, posts, reels e UGC usam a data de **publicação** (UTC); perfis não têm publicação, então usam a data da **captura**.

## Custo da Coleta

O bloco `custo` do manifesto separa o que se previa gastar, o que a Apify cobrou e a diferença. Todo valor tem a unidade no nome: `_usd` são **dólares** (a Apify cobra em dólar; nada é convertido) e `_itens` é a quantidade de resultados. Cada bloco traz `perfis`, `posts`, `reels` e `ugc`, mais o `total`.

| Chave | Conteúdo |
|---|---|
| `estimado.estimado_usd` | previsão do gasto, **média + 3 desvios-padrão do total**, nunca acima do máximo |
| `estimado.maximo_usd` | gasto no limite absoluto: o teto de itens por perfil cheio em todos os perfis |
| `estimado.resultados_itens` | itens por trás do estimado |
| `estimado.teto` | `aplicado_itens_por_perfil` (o limite enviado ao scraper) e `padrao` (`true` se veio do padrão, sem `--teto`) |
| `estimado.base_calibracao` | a Coleta que calibrou posts, reels e UGC, ou `sem_base` |
| `real.custo_usd`, `real.resultados_itens` | o que a Apify cobrou e os itens que devolveu, lidos do run finalizado |
| `diferenca.custo_pct`, `diferenca.resultados_pct` | `(real − estimado) / estimado × 100`, só em percentual; **negativo = abaixo do estimado** |

**Como o estimado é calculado.**

1. **Máximo.** `teto aplicado × nº de perfis × preço por item` de cada coleção (mais a taxa fixa de partida do actor de reels). Sem `--teto`, o teto padrão é `max(200, 7 × dias da janela)` com janela e 30 sem janela. Perfis custam um resultado por governador.
2. **Base de calibração.** É a Coleta anterior mais recente, por menor que seja a janela dela. A contagem de itens de cada governador vem da cobertura por perfil do manifesto dela. Sem base, o estimado de cada coleção é o máximo.
3. **Projeção por governador para o novo Recorte.** Posts e reels: itens ÷ dias da janela da base × dias da nova Coleta. UGC não depende da janela: usa a contagem da base. Todos limitados ao novo teto. Governador que atingiu o teto da base está censurado (a quantidade real é maior) e sobe direto ao novo teto. Governador que estava na base e não teve itens conta zero; se o elenco cresceu desde a base, só os governadores a mais entram com a média dos demais.
4. **Média + 3σ no total.** Com `N` governadores, `v_i` o valor projetado de cada um e `σ` o desvio-padrão (populacional) entre os `v_i`: `estimado_itens = Σ v_i + 3 · √N · σ`, arredondado para cima e limitado ao máximo. Multiplicar por `√N` (e não por `N`) trata o total como a soma de `N` contagens independentes. Aplicar média + 3σ perfil a perfil só reproduziria o teto, porque o desvio entre governadores mede quanto eles diferem entre si, e não o acaso de cada um.
5. **Em dólares.** `itens ÷ 1.000 × preço por 1.000 resultados` do actor e do plano da conta Apify (tabela verificada em 2026-10-13).

Como o estimado é uma previsão alta de propósito, a diferença costuma ser **negativa**: ela mede a folga do orçamento, não o erro da previsão.

**Esta Coleta.** É a primeira, então não tem base de calibração: o estimado é igual ao máximo, US$ 6,31 (teto 30 × 26 perfis = 780 itens por coleção). O custo real foi de US$ 3,72 (perfis 0,07, posts 1,62, reels 1,36, UGC 0,66), cerca de 41% abaixo do estimado. O custo real foi lido dos quatro runs na conta Apify (plano FREE) e o estimado foi recalculado depois com a regra atual, porque a previsão da época não foi gravada.

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
