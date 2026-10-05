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
   cedo. Na média de "Todos", cada estágio considera só governadores com dado real naquele estágio
   (valor positivo); zero significa "sem dado" e puxaria a média para baixo.
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

## Como ficou implementado (conferência no fechamento da spec #182, issue #193)

Os itens 1 a 4 da Decisão foram entregues como descritos. O item 5 era provisório (a sub-aba NSM só herdava a
frase de decisão e os KPIs, e o Scorecard mostrava "em construção"): as fatias seguintes substituíram isso
pelas versões finais abaixo, e a lacuna temporária das Consequências foi fechada pelos gráficos de linha de
Comparar perfis (issue #185). Decisões tomadas durante as ondas que esta ADR não previa e que passam a valer:

- **Sub-aba NSM (issue #187).** Mantém a frase de decisão e os KPIs e ganha cartões (NSM do selecionado, melhor
  aprovação, maior rejeição) e o contraste de dois rankings top 10 com etiquetas SUBIU/CAIU. O selecionado é
  destacado mesmo fora do top 10. O NSM de `governor_nsm` é uma razão sem teto, então é **exibido como índice de
  0 a 100 por normalização min-máx entre os perfis com NSM** (100 = líder; mesma normalização do Scorecard); o
  valor bruto não aparece. O "engajamento bruto" do ranking comparado é o **`total_engajamento`** de
  `governor_nsm` (volume de curtidas + comentários): a medida exata usada na verificação da ADR 0020 ("25 de 27
  perfis mudam de posição") não é recuperável com segurança, então esta é a leitura direta e serve de
  *fallback* até que alguém defina outra. Contra o dado de 2026-10-04 (26 perfis) o ranking por NSM diverge
  desse bruto em 20 perfis. Em "Todos os Governadores" o cartão de NSM é a média simples dos perfis e nada é
  destacado nos rankings.
- **Sub-aba Funil.** Segue o item 3 da Decisão: em "Todos" cada estágio é a média por governador considerando só
  quem tem valor positivo naquele estágio. Nenhuma ação aponta para o Funil hoje; o mecanismo de abrir uma
  sub-aba a partir de outra Tela (`session_state`) existe mas não é usado.
- **Sub-aba Scorecard (issue #188).** Só lê `governor_scorecard`; o selecionado é destacado na tabela
  (sem destaque em "Todos"), as barras por dimensão usam o valor normalizado 0-100 e a dimensão pendente mostra
  "pendente". O selo de confiabilidade traz as duas ressalvas da ADR 0030 (Consistência não é crescimento de
  audiência; Alcance é reproduções).
- **Comparar perfis (issues #185 e #189).** As barras "Seu perfil vs. média dos pares" viraram linhas mensais
  conforme o item 4. A seção "Governadores do grupo" virou a análise de clusters de reels: um botão por cluster
  **realmente presente** em `governor_clusters_reels` (hoje 2 clusters, de 132 e 2 reels, em vez dos 3
  clusters ilustrativos do protótipo, que vêm do Cap. 5 do TCC e não são reproduzidos).
  Os clusters são numerados por tamanho ("Cluster 1" é o maior; o id bruto nunca aparece), o ruído (`-1`)
  aparece como "Casos atípicos / virais", nome, descrição e "O que fazer" saem de regras que comparam o cluster
  com a mediana global (limiares nomeados no código, não calibrados), aviso de poucos reels abaixo de 5 e selo
  "agrupamento experimental" sempre visível. Escopo global (todos os perfis), com a linha do governador
  selecionado.
- **O que produzir (issues #190, #191 e #192).** A fila de temas de comentário foi trocada pela **fila de
  pautas** (assunto da legenda), ranqueada pelo Score ICE de `content_topic_priority_score`: ranking global
  de todos os perfis, filtrado às pautas em que o governador tem reel; `score`, contagem e selo seguem globais
  (tercis do ranking global, como na ADR 0028). O filtro por selo e o popup de comentários da ADR 0028 foram
  mantidos, agora sobre pautas. Abaixo da fila entra "Maiores grupos de comentários" (5 maiores grupos
  positivos e negativos do governador selecionado, ruído fora, popup filtrado por governador e sentimento).
  Pautas degeneradas ("sem assunto definido") nunca são recomendadas. Até o refino real via Gemini ser rodado,
  os rótulos de pauta são os provisórios do BERTopic.
- **Ponto em aberto.** A Lambda `model` ainda não roda os estágios novos (Escore composto, ICE de pautas); ver
  README.
