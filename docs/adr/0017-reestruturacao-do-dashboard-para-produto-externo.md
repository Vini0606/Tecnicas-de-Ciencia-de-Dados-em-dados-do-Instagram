---
status: accepted
---

# Reestruturar o dashboard de "visualização acadêmica de TCC" para produto voltado a público externo

## Contexto

O handoff de 2026-08-31 (sessão de monitoramento diário, ADR 0016 + PR #49 + PR #51) registrou o
próximo pedido do usuário: não um ajuste incremental, mas um reposicionamento completo do
dashboard Streamlit — de "visualização acadêmica de TCC" para um produto útil a governadores,
assessores, jornalistas e curiosos por métricas de redes sociais. O handoff apontou que isso muda o
que "boa visualização" significa aqui (linguagem, hierarquia de informação, paleta) e sugeriu
`/grilling` antes de qualquer `/to-spec`/código, dado que "página que agrega valor pra jornalista" é
decisão de produto, não algo derivável do código existente.

Antes do grilling, o estado do dashboard era: `app.py` (home estática), `pages/01_exploratory.py`
(perfis/engajamento/correlações, filtros de grupo), `pages/02_modeling.py` (sentimento/tópicos/
clusters, seletor de governador próprio), `pages/03_monitoring.py` (tendência de engajamento via
`governor_engagement_history`, único histórico em Gold existente — ver ADR 0016/PR #49). Os seams
testados (`src/dashboard/loaders.py`, `src/visualization/charts.py`) deveriam ser preservados.

Uma rodada de `/grilling` (pergunta a pergunta, com recomendação, mesmo padrão da ADR 0016) resolveu
as decisões de produto em aberto.

## Decisão

1. **Público prioritário desta rodada: governadores/assessores.** Jornalistas e curiosos ficam para
   rodadas futuras de refinamento, mas a base de dados/infra construída (seletor global, histórico de
   sentimento) já serve aos três.
2. **Job principal do público prioritário: "como estou indo vs. meus pares"** — comparação e
   tendência, não só a trajetória isolada do próprio perfil nem só o sentimento do momento.
3. **Seletor de governador global e persistente**, guardado em `st.session_state`, válido em todas as
   páginas (substitui o seletor próprio de `02_modeling.py` e o multiselect próprio de
   `03_monitoring.py`). Sempre com opção "todos" para uso exploratório/comparativo.
4. **Esqueleto de páginas**: Home (visão geral) → **Performance** (funde `03_monitoring.py` com as
   métricas-chave de `01_exploratory.py`, foco comparativo com histórico) → **Insights** (evolução de
   `02_modeling.py`: sentimento/tópicos/clusters, linguagem menos técnica) → **Explorar** (o que sobra
   de `01_exploratory.py`: correlações livres, mais para público analítico/jornalista) →
   **Recommendations** (nova).
5. **Recommendations é híbrido**: um motor de regras/heurísticas determinístico calcula os achados
   (ex.: "engajamento caiu X% nas últimas N execuções", "pares do mesmo cluster postam Y% mais reels
   curtos", "sentimento negativo concentrado no tópico Z") a partir dos dados reais — sem depender de
   LLM, sem custo/latência por execução, sem risco de alucinar números. Redação em linguagem natural
   via LLM por cima das regras fica como refinamento futuro, **não bloqueia o MVP** desta página.
6. **Histórico de Gold estende para sentimento antes das páginas novas**: nova tabela
   `governor_sentiment_history`, mesmo padrão `mode=append` de `governor_engagement_history`
   (ADR 0016/PR #49) — ao lado de `governor_sentiment`, que continua `overwrite`, sem mudança para os
   consumidores existentes. Histórico de clusters (`governor_clusters`/
   `governor_profile_clusters_engagement`) fica deferido — menor frequência de mudança, não é central
   para o MVP de Performance/Insights/Recommendations.
7. **Ordem de implementação**: `governor_sentiment_history` (Gold) → seletor global de governador
   (infra de UX compartilhada) → Home → Performance → Insights → Explorar → Recommendations. Cada
   item como spec pequena via `/to-spec` → `/implement` → `/code-review`, na sequência — mesmo padrão
   já validado nas sessões anteriores (issue #50 → PR #51), evitando uma reestruturação monolítica.

## Por que

- Comparação com pares como job principal: resposta direta do usuário à pergunta sobre o que um
  governador/assessor resolve ao abrir o dashboard — rejeitou tanto "trajetória isolada" quanto "só
  sentimento do momento" em favor de comparação, que já encaixa com o histórico de engajamento
  existente e o cluster de perfil por engajamento (Fase 2) já calculado.
- Seletor global: consequência direta do job de comparação — reselecionar o governador a cada troca
  de página atritaria exatamente a experiência que o produto deveria entregar.
- Esqueleto de páginas: confirmado pelo usuário como proposto, preservando a lógica de "uma página por
  preocupação" que a estrutura atual já usa, só renomeada/reagrupada para a audiência nova.
- Recommendations híbrido com LLM adiado: o usuário rejeitou tanto "regras puras" (sem opção de
  redação natural) quanto "LLM gera tudo" (grounding arriscado sobre números reais) em favor do
  híbrido, mas explicitamente colocou a camada de LLM como refinamento não bloqueante — mesmo
  raciocínio de escopo mínimo já usado no projeto (ver ADR 0010, adiar o que não tem caso concreto
  ainda).
- Histórico de sentimento antes das páginas: mesma ordem de dependência já usada na ADR 0016
  ("histórico em Gold primeiro, dashboard depois") — sem tendência de sentimento, Insights/
  Recommendations mostrariam só o estado da última execução de modelagem.
- Clusters sem histórico por ora: não perguntado como prioridade nesta rodada; mesmo raciocínio de
  "sem caso concreto ainda" que a ADR 0016 já usou para os mesmos dados.

## Opções consideradas

- **Grilling amplo cobrindo os três públicos de uma vez** — rejeitado; o usuário escolheu
  governadores/assessores como prioridade #1 explícita, deixando jornalistas/curiosos para rodadas
  futuras de refinamento sobre a mesma base.
- **Manter seletor de governador por página** (como hoje) — rejeitado; atritaria o job principal de
  comparação contínua entre páginas.
- **Absorver "Explorar" dentro de Insights/Performance, sem página própria** — considerado e
  rejeitado pelo usuário; manter página própria evita misturar o público analítico/jornalista com o
  fluxo comparativo do governador/assessor na mesma tela.
- **Recommendations 100% regras** ou **100% LLM** — ambas rejeitadas explicitamente a favor do
  híbrido (fatos por regra, redação por LLM como camada opcional futura).
- **Estender histórico de Gold para sentimento E clusters já nesta rodada** — rejeitado; usuário
  priorizou só sentimento agora, clusters ficam deferidos pelo mesmo raciocínio já usado no projeto.
- **Dashboard/páginas primeiro, histórico de sentimento depois** — rejeitado; mesma ordem de
  dependência da ADR 0016 (dado antes de UI).

## Consequências

- **Não implementado nesta sessão ainda** (documentado aqui como plano, a ser executado spec por spec
  via `/to-spec`→`/implement`→`/code-review`): `governor_sentiment_history`, seletor global de
  governador em `st.session_state`, e as páginas Home/Performance/Insights/Explorar/Recommendations
  redesenhadas. Esta ADR registra a decisão de produto e a ordem; cada spec individual detalha o
  desenho técnico (schema exato, componente do seletor, wireframe de cada página) no momento da
  implementação.
- `pages/01_exploratory.py` e `pages/02_modeling.py` deixam de existir como estão — seu conteúdo é
  redistribuído entre Performance/Insights/Explorar, não descartado.
- `pages/03_monitoring.py` é absorvida por Performance, não mantida como página separada.
- Histórico de clusters continua fora de escopo até haver necessidade concreta — mesma situação da
  ADR 0016, agora também para `governor_clusters`/`governor_profile_clusters_engagement`.
- A camada de redação via LLM em Recommendations fica registrada aqui como decisão futura, não
  esquecida: se implementada, precisa de grounding cuidadoso (o texto não pode divergir dos números
  calculados pelas regras).
