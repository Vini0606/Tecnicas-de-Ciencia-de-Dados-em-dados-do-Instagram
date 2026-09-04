---
status: accepted
---

# Realinhar métrica de engajamento e adicionar matriz de quadrantes ao relatório da VHL, sem construir produto para deputados

## Contexto

O handoff de 2026-09-03 (fim da reestruturação do dashboard, ADR 0017 + issues #52-#68 mergeadas)
registrou como próximo passo do usuário decidir como o TCC (governadores) e um produto comercial da
VHL Comunicações (deputados) coexistiriam a partir do mesmo código, com o dashboard virando template
de produto. As ADRs [0004](0004-manter-pipelines-separados-por-entidade-sem-generalizar-schema-agora.md)
e [0006](0006-integrar-scraping-de-deputados-via-api-de-dados-abertos-da-camara.md) já tinham desenhado
(sem implementar) como uma segunda entidade política entraria no Medallion.

Nesta sessão, o documento `VHL_Plano_de_Acao_Reconstrucao_Tese_Vendas.docx` (24/08/2026, sócios
Vinícius/Henrique/Luan) foi lido por completo. Ele diagnostica que a tese de vendas atual da VHL
("Grande Dicotomia" / vídeo pesa 2,44× mais que seguidores) é estatisticamente furada — regressão
circular (visualizações prevendo curtidas, o mesmo fenômeno medido duas vezes) e confusão entre
volume (curtidas) e o engajamento real que o próprio Manual de Operações da VHL define (comentários +
salvamentos + compartilhamentos). Propõe um plano de reconstrução em 6 fases e identifica este
repositório como o protótipo funcional do "motor" que a VHL queria (Playbook do Gêmeo Digital).

Durante `/grilling` desta sessão, o usuário cortou o escopo antes de qualquer decisão de arquitetura
multi-entidade: **não haverá dados de deputados nesta rodada, nem repositório/dashboard novo**. O
pedido concreto é alinhar o dashboard **dos governadores já existente** ao que o relatório da VHL
pede metodologicamente, usando só os dados já coletados. ADR 0004/0006 continuam válidas como desenho
para quando uma segunda entidade for implementada de fato — nada aqui as revoga.

Inspeção do código nesta sessão confirmou dois pontos que mudaram o desenho:

- `src/data_extract/scraper.py` já tem os três scrapers que a VHL pede (Profile/Post/Reel), mas
  nenhum schema (`schemas_delta.py`, `schemas.py`) tem campo de `shares`/salvamentos, e nenhuma
  chamada passa `includeSharesCount`/`includeTranscript` via `extra_run_input`. A fórmula de
  engajamento da VHL (`curtidas×1 + comentários×Wc + shares×Ws + salvamentos×Wv`) depende de dados
  que a coleta nunca trouxe para os governadores.
- `% ENGAJAMENTO` (`EngagementAggregator`, `src/features/gold/engagement_aggregator.py`) já é
  `(comentários + curtidas) / seguidores` — estruturalmente igual à fórmula da VHL, só sem pesar
  comentário mais que curtida (peso implícito 1 para os dois). O gap real é o peso, não a fórmula.
- `governor_profile_clusters_engagement` (ADR 0017 Fase 2, `scripts/run_profile_clustering_engagement.py`)
  clusteriza os 27 governadores por `% ENGAJAMENTO`/`RECENCIA`/`FREQUENCIA` via `AutoClusterHPO` — K
  clusters descobertos automaticamente, **sem usar `followersCount`**. A matriz de quadrantes que a
  VHL pede (corte por mediana de audiência × engajamento, 4 rótulos fixos: Inexpressivo/Gigante
  Adormecido/Nicho/Superstar) é um mecanismo diferente — geometria de dispersão, não clustering. A
  suspeita do handoff anterior ("talvez `governor_profile_clusters_engagement` já resolva a matriz")
  estava só parcialmente certa: mesma granularidade (perfil), mecanismo diferente.
- `src/dashboard/recommendations.py` (motor de regras da página Recommendations, ADR 0017) já é
  100% funções puras sobre DataFrames Gold já carregados pelo dashboard — não é um estágio de
  pipeline persistido. `governor_engagement_history` tem só 1 execução registrada até agora — sem
  série histórica real para uma mudança de fórmula quebrar.

## Decisão

1. **Sem produto para deputados nesta rodada.** ADR 0004/0006 continuam como desenho futuro, não
   implementado. Nenhum repositório novo, nenhum dashboard novo, nenhum dado de deputados.
2. **`% ENGAJAMENTO` é substituído no lugar** (mesma coluna, mesmo schema Gold) por
   `(curtidas × 1 + comentários × Wc) / seguidores`, com `Wc > 1`. Shares e salvamentos ficam de fora
   da fórmula — a coleta atual não os captura — e essa ausência é documentada aqui como limitação
   conhecida, não corrigida nesta rodada (sem re-scraping dos 27 governadores).
3. **`Wc` é calibrado empiricamente a cada execução**, como razão `curtidas totais / comentários
   totais` da base dos 27 governadores na execução mais recente — não um valor fixo hardcoded. Segue
   literalmente a recomendação da VHL ("pela raridade relativa de cada ação na base").
4. **Regressão nova com preditores (Fase 3 do relatório: formato, tema, duração, horário, frequência,
   `paidPartnership`, teste de circularidade, validação fora da amostra) fica fora de escopo desta
   rodada.** Vira trabalho de uma rodada futura, potencialmente como análise/pipeline separado.
5. **Matriz de quadrantes é uma feature nova e independente do clustering comportamental
   existente.** Corte por mediana de `followersCount` × `% ENGAJAMENTO` (já corrigido), 4 rótulos
   fixos. Calculada no lado do dashboard, no mesmo padrão de `src/dashboard/recommendations.py`
   (função pura sobre `governor_engagement` já carregado) — não vira tabela Gold nova nem exige
   pipeline stage. `governor_profile_clusters_engagement` continua como está, sem mudança.
6. **A matriz entra na página Performance**, que já é a página de comparação-com-pares (job
   principal do dashboard, ADR 0017) e já tem o histórico de engajamento — mesma família de
   pergunta que a página já responde.
7. **Recommendations ganha regra(s) nova(s)** usando a métrica corrigida e a classificação de
   quadrante (ex.: "engajamento honesto caiu X%", "você está no quadrante Inexpressivo/Gigante
   Adormecido/Nicho/Superstar").
8. **Fora de escopo, explicitamente**: qualquer coisa específica do produto comercial da VHL —
   anonimização de pares em benchmark, LGPD, linguagem de funil/pitch comercial, Playbook do Gêmeo
   Digital. Essas preocupações só fazem sentido quando (e se) um produto VHL real existir neste
   código, o que não é o caso agora.

## Por que

- O usuário cortou explicitamente o escopo multi-entidade nesta rodada — insistir nele seria
  redesenhar algo que ADR 0004/0006 já cobrem como decisão futura, sem caso real (deputados) para
  validar contra, mesmo raciocínio de "não generalizar sem caso concreto" já usado no projeto.
- Substituir `% ENGAJAMENTO` no lugar, em vez de manter duas métricas, evita a confusão de "qual
  engajamento usar" que o próprio relatório da VHL aponta como um dos três defeitos da tese
  atual — e o custo de quebrar continuidade histórica é hoje próximo de zero (1 execução gravada).
- Adiar shares/salvamentos em vez de re-raspar agora evita gastar créditos Apify e reabrir a Fase 1
  antes de validar se a mudança de peso (Wc) já resolve o problema central apontado (curtidas
  tratadas como engajamento) — mesma lógica de escopo mínimo já usada nas ADRs 0004/0005/0010.
- Adiar a regressão nova (Fase 3) evita transformar uma correção de métrica em um projeto de
  modelagem completo (novos preditores, teste de circularidade, validação fora da amostra) na mesma
  rodada — escopo maior, risco de nunca fechar nada.
- Matriz de quadrantes como feature independente do clustering comportamental evita forçar uma
  correspondência artificial entre um cluster livre (K descoberto por `AutoClusterHPO`, sem
  `followersCount`) e 4 categorias fixas de outro conceito (corte de mediana por audiência) — os dois
  mecanismos respondem perguntas diferentes e continuam como visões complementares, não uma
  substituindo a outra.
- Calcular a matriz no dashboard, não em Gold, segue o padrão já validado de
  `src/dashboard/recommendations.py`: é uma derivação barata (27 linhas, mediana + comparação) sobre
  dado já carregado, sem necessidade de persistência nem de rodar como estágio de pipeline.
- `Wc` calibrado empiricamente por execução, em vez de fixo, segue literalmente o método que a VHL
  recomenda e evita arbitrar um número sem base nos dados reais dos 27 governadores.
- Excluir explicitamente LGPD/anonimização/funil comercial evita que preocupações de um produto que
  não existe neste repo (VHL/deputados) vazem para o dashboard acadêmico do TCC — seguem registradas
  aqui como fora de escopo, não esquecidas, para quando (e se) o produto VHL for revisitado.

## Opções consideradas

- **Reraspar os 27 governadores agora para capturar shares/salvamentos** — rejeitada por ora: gasta
  créditos Apify antes de saber se a correção de peso (Wc) já resolve o problema central; fica como
  opção para uma rodada futura se a VHL insistir em ter shares/saves na fórmula.
- **Não mexer na métrica agora, só ajustar linguagem/apresentação** — rejeitada: deixaria o defeito
  central que o relatório aponta (curtidas pesando igual a comentário) sem correção, que é o ponto
  mais barato e mais citado do documento.
- **Incluir a regressão nova (Fase 3) já nesta rodada** — rejeitada: escopo muito maior (novos
  preditores, teste de circularidade, validação fora da amostra) para a mesma rodada da correção de
  métrica; usuário escolheu escopo menor primeiro.
- **Manter `% ENGAJAMENTO` como está e adicionar `% ENGAJAMENTO_V2` ao lado** — rejeitada: dado que
  `governor_engagement_history` não tem série histórica real a proteger, manter duas métricas só
  criaria ambiguidade sobre qual usar em Performance/Recommendations.
- **Estender `governor_profile_clusters_engagement` para incluir `followersCount` e mapear os
  clusters resultantes para os 4 rótulos da VHL** — rejeitada: força correspondência entre um
  mecanismo de cluster livre e 4 categorias fixas de outro conceito, risco de não bater.
- **Matriz de quadrantes como tabela Gold persistida** — rejeitada: over-engineering para uma
  derivação de 27 linhas que já tem um padrão dashboard-side validado (`recommendations.py`); sem
  necessidade de rodar como pipeline stage.
- **Página nova dedicada à matriz de quadrantes** — rejeitada: Performance já é a página de
  comparação-com-pares; uma 6ª página aumentaria a superfície de navegação sem necessidade.
- **Incluir LGPD/anonimização/funil comercial nesta rodada** — rejeitada: essas preocupações são do
  produto comercial da VHL, que não existe neste repositório agora; fora de escopo por decisão
  explícita do usuário.

## Consequências

- **Não implementado nesta sessão ainda** — esta ADR registra a decisão de escopo e desenho; a
  implementação (mudança em `EngagementAggregator`, nova função de classificação de quadrante em
  `src/dashboard/`, gráfico em Performance, regra(s) nova(s) em `recommendations.py`) fica para uma
  spec/issue futura, mesmo padrão de `/to-spec`-como-issue já usado nas rodadas anteriores.
- A ausência de shares/salvamentos na coleta dos governadores continua como limitação conhecida e
  documentada — qualquer apresentação da métrica de engajamento corrigida precisa comunicar isso.
- `Wc` muda a cada execução (recalculado sobre a base corrente), o que significa que o valor exato do
  peso não é comparável entre execuções — só o `% ENGAJAMENTO` resultante é. Isso deve ficar claro se
  o peso for exposto em algum lugar do dashboard.
- `governor_profile_clusters_engagement` (cluster comportamental) e a matriz de quadrantes (corte por
  mediana de audiência × engajamento) coexistem como duas visões de perfil diferentes — nenhuma
  substitui a outra, e um consumidor futuro não deve presumir que são a mesma coisa.
- A regressão com novos preditores (Fase 3 do relatório da VHL) continua pendente — quando entrar,
  precisa decidir se reconcilia ou substitui a métrica de engajamento desta ADR, e se roda como
  análise pontual ou vira estágio de pipeline.
- Qualquer trabalho futuro de produto para a VHL (deputados, anonimização, funil comercial) parte do
  zero em relação às decisões desta ADR — nada aqui adianta esse desenho, só documenta que foi
  deliberadamente deixado de fora.
