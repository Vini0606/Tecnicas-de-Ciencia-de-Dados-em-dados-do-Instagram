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
4. **Engage mostra o volume de UGC orgânico**, em bloco separado abaixo do funil: o número de posts de UGC
   orgânico do governador (média entre os governadores com UGC em "Todos"). É o "volume de UGC" do nível Criar
   do COBRA (ADR 0020). O bloco é separado porque o volume de UGC pode superar o de Convert (dezenas) e
   quebraria o afunilamento. A taxa Convert→Engage (posts de UGC por comentário positivo) aparece num selo entre o
   funil e o bloco, mas nunca entra no gargalo, porque as unidades e as populações são diferentes. Isso **revisa a
   decisão 4 da issue #114**: o módulo passa a ler `governor_ugc_mentions` (via
   `dashboard/core/data.py::load_ugc_mentions`), e o teste estático de proibição foi removido, substituído por
   testes do cálculo.
5. **Os dados atuais são uma amostra de teste, e a tela se adapta sozinha à coleta completa.**
   _(A ocultação do comparativo descrita neste item foi revista pelo ADR
   [0033](0033-comparativo-vs-mediana-no-nsm-rankings-completos-com-rolagem-e-engage-sempre-comparado.md):
   o ▲/▼ do Engage agora aparece sempre.)_ O piloto coletou
   no máximo 5 posts por governador, então a contagem reflete o teto da coleta. Enquanto o máximo de posts por
   governador for menor ou igual ao teto (`_ugc_e_amostra_piloto`), o comparativo ▲/▼ do Engage fica oculto (comparar contagens saturadas é ruído). Com uma coleta
   completa, o comparativo contra a mediana dos demais aparece, sem mudança de código. A tela não exibe aviso de "piloto" (pedido do usuário), então, enquanto a
   amostra for de teste, a taxa Convert→Engage reflete o teto da coleta.
   Duas métricas foram descartadas na prototipagem: a soma de curtidas + comentários (um único post viral
   concentrava 98% da soma de um governador e fazia o comparativo mostrar "▲ 1074%") e a mediana de
   engajamento por post (cada mediana saía de no máximo 5 posts).

## Consequências

- **Com os dados de teste, o número do Engage não discrimina governadores.** 15 dos 20 governadores com UGC têm
  exatamente 5 posts (o teto), 3 têm 4, um tem 2 e outro tem 1; 19 dos 26 governadores do Funil têm UGC. Os
  posts não têm janela de tempo (de 2013 a 2026) e 53 dos 91 não têm `videoPlayCount`. Quando a coleta
  completa existir, vale decidir se a contagem deve usar uma janela de tempo (como os demais estágios) e se
  "Todos" deve usar mediana em vez de média, já que o volume de UGC tende a ser muito concentrado em poucos
  governadores.
- **A população dos estágios não coincide.** Reach soma visualizações só de reels; Act é `likesSum` do perfil
  inteiro (mediana de 1,64 vez as curtidas só dos reels, até 16,7 vezes); Convert conta comentários positivos
  de reels. A taxa Reach→Act mistura populações. Fica como ponto em aberto: trocar o Act por curtidas só de
  reels mudaria a definição do estágio.
- **Comparativo sem significância estatística.** "▲ 129%" em Convert pode vir de poucas dezenas de
  comentários.
- A decisão 4 da issue #114 e a nota da ADR 0020 sobre o Engage pendente ficam superadas neste ponto.
