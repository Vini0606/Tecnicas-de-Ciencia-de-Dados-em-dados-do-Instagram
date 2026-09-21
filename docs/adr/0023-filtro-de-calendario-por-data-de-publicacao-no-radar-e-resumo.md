---
status: accepted
---

# Filtro de calendário por data de publicação na linha do tempo do Radar e no destaque de sentimento do Resumo

## Contexto

A ADR [0021](0021-dashboard-organizado-por-decisao-com-funil-como-tela-dedicada.md) (ponto de atrito 4)
já tinha decidido que nenhuma tela deveria usar linguagem de calendário ("semana", "últimos 7 dias")
porque o pipeline não tem agendamento fixo (execuções são manuais/ad hoc; o agendamento via lambda AWS
continua pendente, ver `[[backfill_lambda_propagation_decision]]` em memória) — "última execução vs.
anterior" pode significar dias ou meses de intervalo. Essa decisão está implementada: `dashboard/core/
deltas.py::week_over_week()` compara as 2 execuções mais recentes por `_run_id`, nunca por calendário
(issue #110), e a linha do tempo original do Radar (`dashboard/screens/radar.py::
_agregar_pct_negativo_por_run`, issue #113) agrega pelas execuções realmente disponíveis, rejeitando
explicitamente "14 dias corridos" na especificação original.

O usuário pediu uma sessão de `/grilling` para revisitar esse filtro por período, achando que a decisão
0021 talvez não coubesse mais dado que ele ainda não sabe a cadência real de coleta. A primeira
exploração do código mostrou que a premissa "calendário vs. execução coexistem hoje" já não é real — a
0021 já unificou tudo em linguagem de execução, e não há nenhuma issue aberta no repositório. A tensão
real, viva no código, era outra: **o tamanho do corte de execuções diverge entre telas** sem
justificativa documentada (`week_over_week`: últimas 2; `resumo._ultimas_execucoes`: últimas 4;
`radar._agregar_pct_negativo_por_run`: sem corte nenhum, todo o histórico).

O grilling então avançou para o que o usuário queria de fato: do ponto de vista do assessor, filtrar
por calendário só faz sentido para dado que tem uma **data real de publicação** independente de quando
a coleta rodou — comentários e discurso oficial (`governor_sentiment`/`governor_sentiment_history`/
`governor_discourse_topics`, todas com coluna `timestamp` própria). Dado de **snapshot de perfil**
(`governor_engagement`: seguidores, % engajamento) não tem essa data por linha — só `minData`/`maxData`
(intervalo agregado da leva) e `_run_id`/`_generated_at` — e continua só filtrável "por coleta".
`governor_clusters` (posts/reels, usado no Funil) não tem nenhuma data própria hoje, nem `timestamp`
nem `_generated_at` por linha própria — fora do escopo desta ADR.

Investigando a viabilidade de agregar por data de publicação, `src/modeling/orchestration.py` (linha
196) mostrou que `governor_sentiment_history` é gravado com `mode="append"` a cada execução — um log
cumulativo entre coletas. A Silver deduplica por `id_comment` **dentro de** cada execução
(`deduplicate_latest`, `src/delta_io.py:35`), mas nada impede o mesmo comentário físico de reaparecer
em `governor_sentiment_history` numa execução futura, se a próxima coleta voltar a puxar posts que já
tinham sido coletados antes — um risco real de contagem duplicada ao agregar por dia de calendário em
vez de por `_run_id`.

## Decisão

**Escopo:** só a Tela 1 (Resumo) e a Tela 3 (Radar de crise). As outras 4 telas (Produzir, Comparar,
Discurso×Reação, Funil) continuam mostrando só o snapshot mais recente, sem nenhuma noção de tempo —
fora de escopo aqui; adicionar um eixo temporal a uma tela hoje puramente "estado atual" é uma decisão
de produto maior que merece sua própria conversa.

**Correção técnica de base (pré-requisito, aplica-se a qualquer leitura de
`governor_sentiment_history` por data de publicação):** deduplicar por `id_comment`, mantendo a
ocorrência de **menor `_run_id`** (a primeira vez que o comentário foi coletado), antes de agregar por
dia. Resolve a contagem duplicada de comentários recoletados em execuções sobrepostas.

**Radar (Tela 3) — linha do tempo (`_agregar_pct_negativo_por_run` é substituída):**
- Eixo X passa de `_run_id` para a data real de publicação do comentário (`timestamp`, parseado como em
  `src/features/silver/post_cleaner.py::_parse_timestamp`).
- Um seletor de calendário (intervalo de datas) controla **só este gráfico** — a frase de decisão
  semafórica e a lista de comentários negativos recentes continuam ancoradas na execução mais recente,
  sempre, independente do filtro: a frase responde "tem algo pegando fogo agora?", e deixar o filtro
  mudar essa resposta faria uma crise antiga parecer atual.
- O filtro abre mostrando **todo o período disponível** no histórico, sem corte padrão — não existe
  cadência de coleta previsível (`resultsLimit=30` por perfil, sem `onlyPostsNewerThan` em produção,
  ver `src/data_extract/scraper.py`/`scripts/run_apify_backfill.py:147`) que justifique um default fixo
  tipo "últimos 14 dias"; um default assim arriscaria abrir a tela vazia para um governador com posts
  mais espaçados.
- Vira gráfico de **linha**, não mais barras.
- Dias sem comentário ficam de fora do gráfico (nunca um "0%" fabricado — mesmo princípio já aplicado
  em `week_over_week`/`_nivel_semaforo`, que preferem `None`/omissão a inventar um valor).
- A linha quebra (gap visível, sem segmento) quando o intervalo entre dois pontos consecutivos com dado
  ultrapassa 7 dias sem nenhum comentário — uma linha contínua ligando pontos distantes sugeriria uma
  tendência que não existe no intervalo sem dado.
- Pontos que cruzam `LIMIAR_NEGATIVIDADE_ALERTA` (30%) ganham marcador vermelho; a linha em si
  permanece em cor neutra — nunca colore o segmento inteiro entre dois pontos, pelo mesmo motivo do gap:
  só sabemos o valor nos dois dias com dado, não no intervalo entre eles.

**Resumo (Tela 1):** um único filtro de calendário, afetando só o destaque "tema com maior alta de
negatividade" (`_maior_alta_negatividade`, mesma fonte de dado do Radar). A faixa de decisão semafórica
e o sparkline de tendência (engajamento/seguidores, via `week_over_week`/`_ultimas_execucoes`) continuam
baseados em execução, sem filtro de calendário — `governor_engagement` não tem data de publicação por
linha para filtrar. Rejeitado explicitamente: dois controles de filtro separados na mesma tela (um
calendário para sentimento, um seletor de coleta para engajamento) — competiriam por atenção numa tela
cujo princípio de design fixo (ADR 0021) é frase de decisão → conteúdo; uma ressalva textual explicando
que engajamento reflete sempre a coleta mais recente é mais barata de entender que um segundo seletor.

**Processo de entrega:** mesmo padrão das ADRs 0019/0020/0021 — esta ADR primeiro, depois issues no
GitHub (`ready-for-agent`), uma por unidade de trabalho, cada uma via TDD e `/code-review`
Standards+Spec antes do merge.

## Por que

- A premissa original do pedido do usuário ("calendário vs. execução coexistem hoje") já não
  correspondia ao código — a ADR 0021 já tinha resolvido isso. Grelhar em cima da pergunta real —
  quando faz sentido usar calendário de publicação vs. calendário de coleta — evitou desfazer uma
  decisão que já estava certa e focou no ponto que de fato ainda estava em aberto.
- Escopo restrito a Resumo e Radar, não as 6 telas: são as únicas duas que já expõem alguma dimensão
  temporal hoje (`week_over_week`, sparkline, linha do tempo). Estender a noção de "filtrar por período"
  às telas de estado-atual mudaria o que elas respondem (de "como está agora" para "como estava em X"),
  decisão de produto separada desta.
- Deduplicar por `id_comment`/menor `_run_id` antes de agregar por publicação: sem isso, um governador
  cujos posts ficam muito tempo circulando (e sendo recoletados em execuções sucessivas) pareceria
  artificialmente mais negativo só por sobreposição de coleta, não por um problema real de percepção
  pública — inverteria o próprio propósito da tela ("Radar de crise").
- Calendário de publicação só na linha do tempo do Radar, nunca na frase de decisão: a frase responde
  uma pergunta com urgência implícita ("agora"); a linha do tempo responde uma pergunta exploratória
  ("como isso evoluiu"). Aplicar o mesmo filtro às duas confundiria as duas perguntas.
- Sem corte padrão de datas: não existe janela de coleta previsível (cada execução pega "os últimos 30
  posts" por perfil, cobrindo de dias a meses dependendo da frequência de postagem de cada governador) —
  um default fixo arriscaria o mesmo tipo de armadilha de calendário-sem-cadência-real que motivou o
  ponto de atrito 4 da ADR 0021.
- Omitir dias sem dado, quebrar a linha após 7 dias de lacuna, e colorir só o marcador (não o segmento):
  as três decisões seguem o mesmo princípio já estabelecido em `deltas.py`/`_nivel_semaforo` — nunca
  desenhar continuidade, tendência ou alerta que o dado real não sustenta.
- Um só filtro no Resumo (não dois controles): o princípio de design fixo da ADR 0021 (frase de decisão
  → conteúdo, sempre a mesma estrutura nas 6 telas) já pesa contra adicionar controles que a analista
  precisaria aprender a diferenciar; uma ressalva textual resolve a mesma necessidade de transparência
  sem essa carga cognitiva.

## Opções consideradas

- **Manter tudo baseado em execução, só uniformizar o corte** (ex.: todas as telas usando as últimas N
  execuções, mesmo N) — rejeitada pelo usuário: não resolve o problema de fundo, que é que dado de
  publicação (comentários) e dado de snapshot (perfil) têm naturezas de tempo diferentes; forçar os dois
  no mesmo corte de execuções esconde essa diferença em vez de expô-la.
- **Um filtro de calendário único cobrindo a tela inteira do Radar** (inclusive frase de decisão e lista
  de comentários) — rejeitada: deixaria a analista filtrar para um período antigo e ver uma faixa
  vermelha de "crise" sobre um problema já resolvido, sem sinalizar que não é mais atual.
- **Dois controles de filtro separados no Resumo** (calendário + seletor de coleta) — rejeitada: complexidade
  de UI desnecessária numa tela cujo princípio de design já é deliberadamente simples (frase → conteúdo).
- **Default de calendário fixo (ex.: últimos 14 ou 30 dias corridos)** — rejeitada: não há cadência de
  coleta real para ancorar esse número; abrir com "todo o período disponível" nunca esconde dado por
  omissão.
- **Eixo contínuo dia-a-dia com dias sem dado marcados visualmente** (em vez de omitidos) — rejeitada:
  com poucos dias reais espalhados num histórico potencialmente longo, o gráfico ficaria majoritariamente
  "vazio marcado", pior para leitura do que só mostrar os dias com dado real.
- **Colorir o segmento da linha inteiro entre dois pontos acima do limiar** (em vez de só o marcador) —
  rejeitada: sugeriria que a negatividade ficou alta durante todo o intervalo entre os dois pontos,
  quando só sabemos o valor nesses dois dias específicos.

## Consequências

- `dashboard/core/deltas.py` ganha uma função de deduplicação por `id_comment`/menor `_run_id`,
  reutilizável por qualquer agregação futura de `governor_sentiment_history` por data de publicação
  (Radar hoje; Resumo se `_maior_alta_negatividade` também migrar para publicação, ver próximo ponto).
- `dashboard/screens/radar.py::_agregar_pct_negativo_por_run` é reescrita para agregar por dia de
  publicação (deduplicado) em vez de por `_run_id`; `render()` ganha um seletor de intervalo de datas
  (`st.date_input` em modo range) e o gráfico Plotly muda de `go.Bar` para `go.Scatter` com `mode="lines
  +markers"`, cor de marcador condicional ao limiar, e quebra de segmento quando o gap > 7 dias.
- `dashboard/screens/resumo.py::_maior_alta_negatividade` passa a respeitar o mesmo filtro de calendário
  do destaque de sentimento — precisa decidir, na issue de implementação, se reaproveita a mesma função
  de agregação por publicação do Radar ou mantém sua própria (ambas operam sobre
  `governor_sentiment_history`, então reaproveitar é o caminho natural).
- `tests/test_dashboard_core_deltas.py`, `tests/test_dashboard_screens_radar.py` e
  `tests/test_dashboard_screens_resumo.py` precisam de casos novos: deduplicação por `id_comment`,
  omissão de dias sem dado, quebra de linha após gap > 7 dias, e marcador vs. segmento colorido no
  limiar.
- `LIMIAR_NEGATIVIDADE_ALERTA` continua a mesma constante única (`deltas.py`), sem mudança — só o jeito
  de exibir o cruzamento do limiar no gráfico do Radar muda (marcador em vez de barra colorida).
- Nenhuma mudança em `governor_engagement`/`governor_clusters` nem nas 4 telas fora de escopo — se um
  filtro de calendário fizer sentido ali no futuro, é uma ADR separada.
