---
status: accepted
---

> **Nota (relacionada):** esta ADR substitui parcialmente o item 4 da Decisão da ADR
> [0027](0027-janela-por-disponibilidade-historico-de-nsm-e-visao-agregada-todos-governadores.md)
> (layout `st.columns([0.75, 0.25])` com gráfico + 3 filtros empilhados). Ver nota equivalente no topo da
> ADR 0027.

# Evidência histórica de desempenho no Resumo: 3 gráficos paralelos (Ambos/Posts/Reels), filtro único de Métrica, sem filtro de período

## Contexto

Sessão de `/grill-with-docs` a partir de um pedido do usuário de 4 mudanças na seção "Evidência histórica
de desempenho" do Resumo (`dashboard/screens/resumo.py`, `render()` linhas ~829-890, introduzida pela ADR
0024 e reposicionada/redesenhada pela ADR 0027 item 4):

1. Remover o seletor "Tipo de conteúdo" (`TIPO_AMBOS`/`TIPO_POSTS`/`TIPO_REELS`) -- em vez de 1 gráfico
   dirigido por esse seletor, renderizar sempre os 3 gráficos ao mesmo tempo.
2. Gráfico "Ambos" em largura total no topo; Posts e Reels lado a lado, 50/50, abaixo dele.
3. Mover o filtro que sobrevive (Métrica, já que Tipo de conteúdo saiu) para uma linha acima dos
   gráficos, largura total -- em vez da coluna lateral de 25% da ADR 0027.
4. Remover completamente o filtro de período (`st.date_input`) -- sempre mostrar o intervalo de datas
   inteiro disponível para a série sendo plotada, sem janela ajustável pelo usuário.

Grilling desta sessão resolveu 4 pontos que o usuário não tinha decidido ainda (ver Decisão itens 3, 5 e
6) contra o próprio usuário, e confirmou por leitura de código (sem precisar perguntar) que:
`filter_by_date_range`/`normalize_date_input_range` são usadas em `resumo.py` só nesta seção (linhas
879-880) -- `radar.py` usa as mesmas funções para seu próprio filtro de calendário, independente, e não é
afetado por essa remoção.

## Decisão

**1. Seletor "Tipo de conteúdo" removido; os 3 gráficos (Ambos/Posts/Reels) renderizam sempre, em
paralelo.** `_conteudo_do_governador_por_tipo`/`_serie_desempenho_por_publicacao` (ADR 0024, inalteradas)
passam a ser chamadas 3x por `render()` -- uma vez por `tipo` de `_ORDEM_TIPOS_CONTEUDO` -- em vez de 1x
com o `tipo` escolhido no selectbox.

**2. Layout: `st.markdown("#### Evidência histórica de desempenho")` → filtro de Métrica em linha cheia →
gráfico "Ambos" em largura total → `st.columns(2)` com Posts e Reels 50/50.** Substitui inteiramente o
`st.columns([0.75, 0.25])` da ADR 0027 para esta seção.

**3. Métrica continua 1 selectbox compartilhado, controlando os 3 gráficos em paralelo** -- não 1 seletor
por gráfico. Os 3 gráficos sempre mostram a mesma métrica ao mesmo tempo; trocar a métrica reflete nos 3
juntos.

**4. Filtro de período (`st.date_input`) removido inteiramente desta seção.** Cada um dos 3 gráficos
mostra o intervalo `data_min`/`data_max` completo da própria série (`df_serie_completa`, sem
`filter_by_date_range`) -- import de `filter_by_date_range`/`normalize_date_input_range` sai de
`resumo.py` (única consumidora dessas 2 funções nesse arquivo); `radar.py` mantém as duas, seu filtro de
calendário é independente e não muda.

**5. Código de construção do gráfico Plotly extraído para uma função auxiliar compartilhada, chamada 3x**
(uma por tipo de conteúdo) -- em vez de duplicar o bloco (`fig = go.Figure()` / loop de
`quebrar_em_segmentos` / `fig.update_layout` / `st.plotly_chart`, hoje ~30 linhas inline) 3 vezes. Recebe
`df_serie` (já filtrado/agregado) + rótulo/título e produz 1 chamada de `st.plotly_chart`; caso vazio
(`df_serie_completa.empty`) continua resolvido com `st.caption(...)` como hoje, mas por gráfico
individual -- ver item 6.

**6. Estado vazio ("sem dado disponível") é por gráfico, nunca um bloqueio global da seção.** Caso
conhecido e esperado: `METRICA_VISUALIZACOES` não existe para `TIPO_POSTS` (posts de feed não têm
`videoPlayCount`) -- o gráfico "Posts" mostra a legenda de ausência de dado enquanto "Ambos" e "Reels"
renderizam normalmente com a mesma métrica selecionada. Nenhuma mudança na mensagem de
`st.caption(...)` já existente (ADR 0024), só no escopo -- 1 gráfico por vez, não a seção inteira.

**7. "Todos os Governadores" (ADR 0027 / issue #161) não precisa de tratamento especial para 3 gráficos
paralelos** -- `_conteudo_do_governador_por_tipo` já delega para `_filtrar_por_governador_ou_todos`, que
já trata `governor_url == TODOS_OS_GOVERNADORES` agregando sem filtro; rodar essa mesma função 1x por tipo
de conteúdo (Ambos/Posts/Reels) já produz o comportamento agregado esperado nos 3, sem lógica nova.

**Processo de entrega:** mesmo padrão das ADRs 0019-0028 -- spec via `to-spec` + issue(s)
`ready-for-agent`, implementação via TDD, `/code-review` Standards+Spec antes do merge.

## Por que

- 3 gráficos paralelos em vez de 1 selecionável: o usuário quer comparar Ambos/Posts/Reels sem precisar
  trocar o seletor 3x e guardar mentalmente os 3 estados -- mesma motivação de visualizar tudo de uma vez
  já aceita para os KPIs (`kpi_row` mostra os 4 KPIs sempre juntos, nunca 1 seletor de KPI).
- Ambos em largura total, Posts/Reels 50/50 abaixo: "Ambos" é a soma dos outros 2 -- hierarquia visual
  (o todo em destaque, as partes menores abaixo) reflete a relação entre os dados sem precisar de legenda
  explicando isso.
- 1 seletor de Métrica compartilhado, não 3 independentes: o usuário pediu "mudar o filtro de lugar" no
  singular -- e comparar Ambos/Posts/Reels só é uma comparação útil quando os 3 mostram a MESMA métrica ao
  mesmo tempo; 3 seletores independentes multiplicaria estados sem um caso de uso claro pedido.
- Filtro de período removido, não só reposicionado: o usuário quer sempre ver o histórico completo
  disponível nesta seção -- consistente com a mudança já feita pela ADR 0026/0027 no resto do Resumo
  (que já não tem filtro de calendário para os KPIs; só esta seção de evidência ainda tinha um, herdado
  da ADR 0024 quando a seção vivia em "O que produzir").
- Função auxiliar de gráfico compartilhada em vez de duplicar 3x: mesmo critério já usado para
  `_conteudo_do_governador_por_tipo`/`_serie_desempenho_por_publicacao` (ADR 0024) -- 1 gráfico chamado 3x
  com parâmetros diferentes é mais fácil de testar e manter do que 3 blocos quase-idênticos divergindo com
  o tempo.
- Estado vazio por gráfico, não bloqueio global: "Posts" vazio para Visualizações é dado real esperado
  (não um erro), então bloquear os outros 2 gráficos por causa disso escondería informação real dos outros
  2 tipos de conteúdo -- mesmo princípio de "nunca esconder dado disponível por causa de outro filtro
  vazio" já usado em toda a tela (ADR 0021/0025/0027).

## Opções consideradas

- **1 seletor de Métrica por gráfico** (3 seletores independentes) -- rejeitada: o pedido do usuário foi
  no singular ("o filtro"), e comparar Ambos/Posts/Reels só faz sentido direto quando os 3 mostram a mesma
  métrica; 3 seletores independentes multiplicaria estados sem um caso de uso pedido.
- **Duplicar o bloco de construção do gráfico Plotly 3x inline** -- rejeitada: mais rápido de escrever,
  mas 3 cópias quase-idênticas tendem a divergir silenciosamente em mudanças futuras (ex.: um ajuste de
  `update_layout` aplicado em 2 dos 3 blocos por esquecimento).
- **Manter filtros numa coluna lateral estreita** (só removendo Tipo de conteúdo e Período, Métrica
  continua ao lado) -- rejeitada pelo usuário: pedido explícito foi mover o filtro para ACIMA dos
  gráficos, em linha cheia, não mantê-lo lateral.
- **Registrar a mudança de layout só como edição silenciosa da ADR 0027** (sem ADR nova) -- rejeitada:
  o layout 75/25 foi uma decisão explícita e documentada (ADR 0027 item 4) menos de 1 semana atrás; uma
  ADR nova com nota de "relacionada" no topo das duas mantém rastreável por que o layout mudou de novo tão
  rápido, mesmo padrão já usado entre ADR 0024 e ADR 0026.

## Consequências

- `dashboard/screens/resumo.py`: seletor "Tipo de conteúdo" (`st.selectbox` com `_ORDEM_TIPOS_CONTEUDO`)
  removido; `render()` passa a chamar `_conteudo_do_governador_por_tipo`/`_serie_desempenho_por_publicacao`
  3x (uma por `tipo` de `_ORDEM_TIPOS_CONTEUDO`); nova função auxiliar de renderização do gráfico Plotly
  (chamada 3x); `st.columns([0.75, 0.25])` da seção sai, entra layout de linha cheia (filtro) + largura
  total (Ambos) + `st.columns(2)` (Posts/Reels); `st.date_input`/`filter_by_date_range`/
  `normalize_date_input_range` saem inteiramente desta seção (import das 2 últimas sai do arquivo).
- `_conteudo_do_governador_por_tipo`, `_serie_desempenho_por_publicacao`, constantes `TIPO_*`/`METRICA_*`
  (ADR 0024) não mudam -- só como/quantas vezes são chamadas por `render()`.
- ADR 0027 item 4 (layout `st.columns([0.75, 0.25])`) fica parcialmente superseded por esta ADR -- nota
  adicionada no topo dos dois arquivos.
- `tests/test_dashboard_screens_resumo.py` precisa de casos novos: 3 gráficos renderizando em paralelo,
  estado vazio isolado por gráfico (Posts + Visualizações vazio, Ambos/Reels não), ausência do filtro de
  período, seletor de Tipo de conteúdo removido.
