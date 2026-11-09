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

A `main` guarda **só a Coleta vigente**. Cada Coleta é um commit, identificado pela mensagem `push: coleta_...` e descrito pelo `manifesto.json`, que é a fonte de verdade sobre o que foi extraído. As Coletas anteriores continuam no histórico do dataset e acessíveis pela tag de uso.

| | |
|---|---|
| **Identificador** | `coleta_2026-11-08_de-2026-08-16_ate-2026-10-25_tcc` (mensagem do commit `c2aef6f0`) |
| **Extração** | 2026-11-08, a partir das 23:19 UTC |
| **Recorte** | de 2026-08-16 a 2026-10-25, **sem teto** |
| **Perfis** | 26 governadores |
| **Tags de uso** | `tcc`, a Coleta do TCC |

**O período.** Do início da propaganda eleitoral (2026-08-16) ao 2º turno (2026-10-25), passando pelo 1º turno (2026-10-04). A pré-campanha ficou de fora de propósito, por custo. O actor da Apify só filtra o início da janela ("mais novo que N dias", aqui 84), então a extração foi até 2026-11-08 e a Coleta descartou depois os itens posteriores a 2026-10-25.

**Sem teto.** Posts, reels e UGC foram extraídos sem limite de itens por perfil. O UGC é o ponto sensível: o actor de marcações não filtra por data e traz as marcações do mais novo ao mais antigo, então a janela só fica completa porque o limite não cortou nenhum governador.

### Cobertura

| Fonte | Itens (Bronze) | Datas |
|---|---|---|
| Posts | 9.637 | 2026-08-16 a 2026-10-25 |
| Reels | 7.202 | 2026-08-16 a 2026-10-25 |
| Perfis | 26 | dados de perfil no momento da extração (2026-11-08) |
| UGC (posts de terceiros que marcam o governador) | 16.849 | 2026-08-16 a 2026-10-25; 17 governadores com marcações, 9 sem nenhuma |

Cinco governadores concentram a maior parte do UGC, cada um com mais de 2.000 itens na janela. A cobertura por perfil está no `manifesto.json`.

**Coleta anterior.** A Coleta do Reboot (`coleta_2026-10-06_ultimos-5d_teto-30`, tag `reboot-iesb`) foi a apresentada no evento da IESB: últimos 5 dias, teto de 30 itens por perfil, 26 governadores, com as tabelas de modelagem. Ela continua acessível: `coleta.py baixar reboot-iesb --destino <pasta>`.

## Estrutura

```
bronze/   dado da Apify, uma tabela Delta por fonte
silver/   dado limpo e conformado
gold/     métricas e modelagem consumidas pelo dashboard
landing/  payload bruto da extração (só na Coleta do Reboot; a `main` ainda a mantém)
manifesto.json
```

- **Bronze:** `instagram_posts`, `instagram_profiles`, `instagram_reels`, `ugc_mentions`. Coletas novas (como a `tcc`) guardam o item completo da Apify na Bronze; a Coleta do Reboot não tem a coluna `_raw` e o payload completo dela está em `landing/`.
- **Silver:** `posts_clean`, `reels_clean`, `profiles_clean`, `comments_clean` (comentários de reels), `post_comments_clean`, `ugc_mentions` e `governors_metadata`.
- **Gold da Coleta `tcc`:** só `governor_engagement`, `governor_engagement_history` e `governor_ugc_mentions`. As tabelas de **modelagem** (NSM, scorecard, clusters, sentimento, tópicos de discurso, prioridade de pautas e regressão de performance) **não foram geradas** nesta Coleta; o dashboard completo depende delas. A Coleta do Reboot (tag `reboot-iesb`) as tem.

O manifesto (esquema v5) traz a identidade da Coleta, o Recorte pedido e a janela efetiva em datas, a cobertura por fonte e por perfil, o custo e a contagem de linhas de cada tabela. Nenhum campo é nulo: o que não se aplica simplesmente não aparece. Na cobertura, posts, reels e UGC usam a data de **publicação** (UTC); perfis não têm publicação, então usam a data da **captura**.

## Custo da Coleta

O bloco `custo` do manifesto separa o que se previa gastar, o que a Apify cobrou e a diferença. Todo valor tem a unidade no nome: `_usd` são **dólares** (a Apify cobra em dólar; nada é convertido) e `_itens` é a quantidade de resultados. Cada bloco traz `perfis`, `posts`, `reels` e `ugc`, mais o `total`.

| Chave | Conteúdo |
|---|---|
| `estimado.estimado_usd` | previsão do gasto, **média + 3 desvios-padrão do total**, nunca acima do máximo |
| `estimado.maximo_usd` | gasto no limite absoluto: o teto de itens por perfil cheio em todos os perfis (não existe numa Coleta sem teto) |
| `estimado.resultados_itens` | itens por trás do estimado |
| `estimado.teto` | `aplicado_itens_por_perfil` (o limite enviado ao scraper) e `padrao`; numa **Coleta sem teto** (sem `--teto`) vale `{"sem_teto": true}` e não há máximo; com `--teto-ugc` (teto só do UGC, ADR 0044) ganha `ugc_itens_por_perfil` e, sem teto geral, o máximo só do UGC em `estimado.maximo_ugc_usd` |
| `estimado.base_calibracao` | a Coleta que calibrou posts, reels e UGC, ou `sem_base` |
| `real.custo_usd`, `real.resultados_itens` | o que a Apify cobrou e os itens que devolveu, lidos do run finalizado |
| `diferenca.custo_pct`, `diferenca.resultados_pct` | `(real − estimado) / estimado × 100`, só em percentual; **negativo = abaixo do estimado** |

**Como o estimado é calculado.**

1. **Máximo.** `teto aplicado × nº de perfis × preço por item` de cada coleção (mais a taxa fixa de partida do actor de reels). Sem `--teto` não há teto nem máximo (Coleta sem teto). Coletas anteriores à v5 sem teto pedido aplicaram `max(200, 7 × dias da janela)` com janela e 30 sem janela. Perfis custam um resultado por governador.
2. **Base de calibração.** É a Coleta anterior mais recente, por menor que seja a janela dela. A contagem de itens de cada governador vem da cobertura por perfil do manifesto dela. Sem base, o estimado de cada coleção é o máximo.
3. **Projeção por governador para o novo Recorte.** Posts e reels: itens ÷ dias da janela da base × dias da nova Coleta. UGC não depende da janela: usa a contagem da base. Todos limitados ao novo teto. Governador que atingiu o teto da base está censurado (a quantidade real é maior) e sobe direto ao novo teto. Governador que estava na base e não teve itens conta zero; se o elenco cresceu desde a base, só os governadores a mais entram com a média dos demais.
4. **Média + 3σ no total.** Com `N` governadores, `v_i` o valor projetado de cada um e `σ` o desvio-padrão (populacional) entre os `v_i`: `estimado_itens = Σ v_i + 3 · √N · σ`, arredondado para cima e limitado ao máximo. Multiplicar por `√N` (e não por `N`) trata o total como a soma de `N` contagens independentes. Aplicar média + 3σ perfil a perfil só reproduziria o teto, porque o desvio entre governadores mede quanto eles diferem entre si, e não o acaso de cada um.
5. **Em dólares.** `itens ÷ 1.000 × preço por 1.000 resultados` do actor e do plano da conta Apify (tabela verificada em 2026-10-13).

Como o estimado é uma previsão alta de propósito, a diferença costuma ser **negativa**: ela mede a folga do orçamento, não o erro da previsão.

**Esta Coleta (`tcc`).** Foi extraída **sem teto**, então não tem custo máximo. A base de calibração foi a Coleta do Reboot (5 dias, teto de 30), e o estimado saiu em US$ 47,05 (posts 24,95, reels 21,15, UGC 0,89, perfis 0,06). O custo real foi de **US$ 85,62**, 82% acima do estimado: posts 23,59 (−5,5%), reels 17,48 (−17,4%), UGC **44,50** (+4.925%) e perfis 0,06. A diferença está toda no UGC: a base tinha teto de 30 por perfil e 5 dias, e não previa que 5 governadores passariam de 2.000 marcações na campanha (a previsão foi de 385 itens, vieram 19.346). Os itens cobrados incluem os 14 dias depois de 2026-10-25, que o actor devolve e a Coleta descarta localmente (o actor não filtra o fim do intervalo): foram cobrados 37.226 itens e mantidos 33.714 (9.637 posts, 7.202 reels, 16.849 UGC e 26 perfis). A conta Apify estava no plano Starter (tier BRONZE); o cupom de desconto da conta vale só na mensalidade, não no preço por item.

## Como usar

- **Dashboard:** baixa `silver/`, `gold/` e `manifesto.json` da `main`. Para mostrar outra Coleta, defina `HF_DATASET_REVISAO` com uma tag de uso ou o hash do commit.
- **Reconstruir as camadas:** a partir de uma Coleta (identificador, tag de uso ou hash de commit), a Lambda `rebuild` (AWS) regenera Bronze, Silver e Gold no S3.
- **Baixar uma Coleta:** `coleta.py baixar <coleta> --destino <pasta>` (identificador, tag de uso ou hash de commit); listar: `coleta.py listar`.

## Convenção de commits e tags

- **Cada Coleta é um commit na `main`.** A mensagem segue o estilo do Git, com o identificador da Coleta na descrição: `push: <identificador>` ao publicar e `restore: <identificador>_restaurada` ao restaurar.
- **Identificador:** `coleta_<data da extração>[_ultimos-Nd | _de-AAAA-MM-DD_ate-AAAA-MM-DD][_teto-N][_teto-ugc-N][_rotulo]`. Não é uma tag; fica na mensagem do commit e no manifesto.
- **Tags são só de uso**, criadas à mão (ex.: `reboot-iesb`, `tcc`, `article-governor-segmentation`). Apontam para o commit de uma Coleta e nunca são movidas nem apagadas pelo projeto. Se a `main` for reescrita (squash), só sobrevivem as Coletas que tiverem uma tag.
- **Restaurar uma Coleta antiga na `main`:** novo commit; nunca force-push.

Convenção completa: `docs/agents/coletas.md` e ADR 0039 no repositório do projeto.
