---
status: accepted
---

# Filtro de período único e exclusão de publicações fixadas nas métricas de publicações

## Contexto

O calendário do Radar (ADR [0023](0023-filtro-de-calendario-por-data-de-publicacao-no-radar-e-resumo.md)) era um
`st.date_input` próprio de uma tela, e as demais telas com métricas de publicações (Comparar) não tinham filtro de
período. Além disso, publicações fixadas no perfil aparecem com datas bem anteriores à janela da extração e
distorcem o período mostrado (issue #281, spec #280).

Investigação da marcação de fixado (Silver local do piloto, Bronze e código):

- A **Bronze de reels** traz `isPinned` (522 linhas: 493 falso, 28 verdadeiro, 1 nulo).
- A **Bronze de posts de feed** não declarava `isPinned` no esquema (`BRONZE_POSTS_SCHEMA`); o campo só sobrevive
  em `_raw` das Bronzes novas.
- Os esquemas Silver (`SILVER_POSTS_SCHEMA`, `SILVER_REELS_SCHEMA`) **não tinham a coluna**, e `conform_to_schema`
  descarta colunas fora do esquema. Por isso `isPinned` sumiu de `reels_clean` e `posts_clean`, embora o
  `PostCleaner.clean_reels` já normalizasse o valor (o resultado era descartado na escrita). O normalizador antigo
  ainda convertia nulo em falso.

## Decisão

1. **A marcação passa a existir na Silver de posts e de reels**: `isPinned` (bool, nullable) entra em
   `BRONZE_POSTS_SCHEMA`, `SILVER_POSTS_SCHEMA` e `SILVER_REELS_SCHEMA`; `PostCleaner` normaliza o campo nas duas
   limpezas e **preserva o nulo** (não o converte em falso). Silvers antigas só ganham a coluna na próxima
   reconstrução (Bronze fiel + `coleta.py`, ADR 0039); até lá a coluna ausente é tratada como nula.
2. **Regra para nulo: nulo (e coluna ausente) = não fixado.** Excluir o nulo apagaria posts legítimos de Bronzes
   que nunca trouxeram o campo; manter um fixado por engano é o erro menor e visível.
3. **A regra de exclusão fica na camada de tela, no núcleo do dashboard, não na Silver.** A Silver continua fiel
   (guarda o fixado e sua marcação); `dashboard/core/periodo.py` (`excluir_fixados`, `filtrar_publicacoes`,
   `limites_de_datas`) aplica a regra nas métricas de publicações. Assim a decisão é reversível sem reprocessar
   dado, e outras leituras da Silver (modelagem, UGC) não perdem linhas.
4. **Um único seletor de período** (`dashboard/core/seletor_periodo.py`): atalho "Todo o período", entrada
   "de DD/MM/AAAA até DD/MM/AAAA" e calendário, com limites presos ao menor e maior dia com dado (fixados não
   contam para os limites). O estado é compartilhado entre telas pela mesma chave. Radar (que perde o calendário
   próprio) e a seção de linhas mensais de Comparar o usam; período sem publicações mostra
   "Nenhuma publicação no período selecionado."

## Consequências

- O Radar filtra comentários por data de publicação do comentário; a exclusão de fixados não se aplica ali (a
  série é de comentários, não de publicações). Só o intervalo e o componente são compartilhados.
- Telas que mostram só o snapshot mais recente (Produzir, Funil, Resumo) não ganharam o seletor: a ADR 0029 manteve
  a evidência de desempenho sem filtro de período, e acrescentar eixo temporal a elas é decisão separada.
- Termo novo no glossário: **Publicação fixada**.
