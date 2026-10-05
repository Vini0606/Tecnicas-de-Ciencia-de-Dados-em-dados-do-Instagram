---
status: accepted
---

# Funil em escala logarítmica, Engage com o engajamento do UGC piloto e comparativo contra a mediana dos demais governadores

## Contexto

A sub-aba Funil do Resumo (ADR [0031](0031-resumo-em-sub-abas-funil-como-sub-aba-e-evidencia-substituida-por-linhas-em-comparar-perfis.md))
mostrava 4 barras horizontais lineares: Reach (visualizações), Act (curtidas), Convert (comentários positivos)
e Engage como texto fixo "em construção". Na verificação visual da feature, dois problemas apareceram:

1. **Escala.** Os estágios diferem em ordens de grandeza (dado real de 2026-10-04, média por governador: cerca
   de 1,37 milhão de visualizações, 118 mil curtidas, 42 comentários positivos). Numa escala linear a barra de
   Convert some, e o código a desenhava com 2% de largura mínima, cerca de 650 vezes maior que o valor real,
   sem avisar. O rótulo "▼ 100% de perda" era, na verdade, 99,96% arredondado.
2. **Engage sem número.** A decisão original da issue #114 proibia qualquer leitura de tabela `ugc_*` (teste
   estático por AST no módulo) e a ADR [0020](0020-alinhamento-tcc-funil-cobra-race-nsm-ice-cmgr-e-reformulacao-do-dashboard-de-growth.md)
   dizia que o Engage só viraria número real quando `governor_ugc_mentions` existisse. A tabela existe desde o
   piloto de 2026-09-19 (91 posts orgânicos, 20 governadores).

## Decisão

1. **Funil de trapézios centralizados, largura em escala logarítmica.** A largura de cada etapa é
   proporcional ao log10 do valor (mínimo de 14% para a etapa com dado ficar visível), e a tela avisa que a
   escala é logarítmica e não proporcional ao volume. Etapa sem dado vira um contorno tracejado "sem dado".
2. **A taxa de passagem fica entre as etapas**, em selos ("▼ 20% avançam"), com o selo "gargalo" na transição
   de menor taxa. Substitui o texto "▼ N% de perda", que passava a ideia de que as etapas são subconjuntos umas
   das outras (são unidades diferentes).
3. **Comparativo dentro da etapa, só com um governador selecionado.** Cada etapa mostra ▲/▼ e a diferença
   relativa do **valor absoluto** da etapa contra a **mediana dos demais governadores** (só quem tem valor maior
   que zero na etapa, mesma regra do resto do módulo). Em "Todos os Governadores" não há comparativo. Mediana,
   e não média: a média é puxada por poucos governadores com valores altos (o máximo de Act→Convert é 2,3%
   contra uma mediana de 0,15%) e chegou a inverter a leitura do mesmo governador na prototipagem. Valor
   absoluto reflete sobretudo o tamanho da audiência, então a seta indica escala, e o selo de taxa indica
   eficiência.
4. **Engage mostra o engajamento do UGC piloto**, em bloco separado abaixo do funil: `SUM(likesCount +
   commentsCount)` dos posts orgânicos do governador (média por governador em "Todos", só entre quem tem UGC),
   com o selo "piloto" e a nota da amostra. O bloco é separado porque o valor do Engage (da ordem de milhares)
   pode superar o de Convert (dezenas) e quebraria o afunilamento. `Convert/Engage` continua não sendo uma taxa
   nem um gargalo. Isso **revisa a decisão 4 da issue #114**: o módulo passa a ler `governor_ugc_mentions`
   (via `dashboard/core/data.py::load_ugc_mentions`), e o teste estático de proibição foi removido, substituído
   por testes do cálculo.

## Consequências

- **O número do Engage é frágil.** O piloto coletou no máximo 5 posts por governador (mediana e máximo são 5),
  então a quantidade de posts é o teto da coleta e não uma medida; o que varia é o engajamento desses poucos
  posts. 19 dos 26 governadores do Funil têm UGC. Os posts não têm janela de tempo (de 2013 a 2026) e 53 dos 91
  não têm `videoPlayCount`. A tela diz isso ("amostra do piloto, até 5 posts por governador"). Revisitar quando
  houver coleta sem o teto.
- **A população dos estágios não coincide.** Reach soma visualizações só de reels; Act é `likesSum` do perfil
  inteiro (mediana de 1,64 vez as curtidas só dos reels, até 16,7 vezes); Convert conta comentários positivos
  de reels. A taxa Reach→Act mistura populações. Fica como ponto em aberto: trocar o Act por curtidas só de
  reels mudaria a definição do estágio.
- **Comparativo sem significância estatística.** "▲ 129%" em Convert pode vir de poucas dezenas de
  comentários.
- A decisão 4 da issue #114 e a nota da ADR 0020 sobre o Engage pendente ficam superadas neste ponto.
