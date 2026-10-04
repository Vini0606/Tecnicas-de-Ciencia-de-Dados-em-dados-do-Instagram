---
status: accepted
---

# Resumo em sub-abas (NSM, Funil, Scorecard), Funil como sub-aba e evidência substituída por gráficos de linha em Comparar perfis

## Contexto

A spec de Scorecard e pautas (issue #182) parte de um problema de navegação: o Resumo mostra KPIs e três
gráficos de evidência de desempenho, mas não ranqueia os 27 governadores nem contrasta engajamento bruto com
engajamento qualificado (NSM), e o Funil de engajamento vive numa Tela separada, longe do contexto do Resumo.
Os protótipos aprovados para a nova versão organizam o Resumo em três visões do mesmo perfil.

Decisões anteriores afetadas: a ADR 0021 manteve o Funil como Tela dedicada (carro-chefe, Opção C híbrida); a
ADR 0029 fixou a evidência histórica no Resumo como três gráficos paralelos (Ambos, Posts, Reels) com filtro
único de Métrica.

## Decisão

1. **Resumo vira um contêiner** com um seletor de governador único (mantendo "Todos os Governadores") acima de
   três **sub-abas**, na ordem NSM, Funil de engajamento, Scorecard. NSM é a sub-aba padrão. "Sub-aba" é o
   termo para a divisão interna; "Tela" continua sendo item da navegação lateral.
2. **O Funil deixa de ser Tela própria** e passa a ser sub-aba do Resumo. Sai da navegação lateral; ações em
   outras telas que apontavam para ele passam a apontar para o Resumo. Esta ADR supera a parte da ADR 0021 que
   mantinha o Funil como Tela dedicada; o restante da ADR 0021 (organização por decisão, funil como espinha
   conceitual) segue valendo.
3. **O Funil segue o seletor único.** Em "Todos os Governadores", cada estágio é a média por governador (cada
   perfil pesa igual, mesma convenção da ADR 0027), e as perdas entre estágios e o gargalo são calculados sobre
   essas médias, nunca sobre somas. As regras de honestidade do Funil são preservadas: rótulo "Visualizações"
   (nunca "Alcance") no primeiro estágio, estágio Engage estático "em construção" sem número, texto sempre
   associativo, taxa sem dado é "sem dado" e nunca zero, gargalo exclui estágios sem dado e desempata pelo mais
   cedo.
4. **A evidência histórica de desempenho sai do Resumo.** Os três gráficos Ambos/Posts/Reels e o seletor de
   Métrica da seção deixam de existir ali. Sua função é assumida por gráficos de linha mensais em Comparar
   perfis (governador contra média e mediana de todos), entregues em fatia posterior da mesma spec. A ADR 0029
   fica **superada** por esta.
5. **Sub-abas Scorecard e NSM evoluem em fatias seguintes.** Até lá, a sub-aba NSM preserva a frase de decisão e
   os KPIs atuais, e o Scorecard exibe um aviso "em construção". Cada sub-aba vive em módulo próprio para que as
   fatias não conflitem.

## Consequências

- A navegação lateral passa a ter cinco Telas.
- Enquanto os gráficos de linha de Comparar perfis não forem entregues, a leitura histórica por publicação
  fica indisponível no dashboard; é uma lacuna temporária aceita pela ordem de fatias da spec.
- A paleta de dado dos componentes novos usa tokens com variante clara e escura, separada do vermelho IESB
  (reservado ao chrome), conforme a decisão anterior de separar chrome e dataviz.
