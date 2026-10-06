---
status: accepted
---

# Comparativo vs. mediana no NSM, rankings completos com rolagem e Engage sempre comparado

## Contexto

Na verificação visual do dashboard (2026-10-05), a analista pediu três ajustes (issue #208):

1. O cartão de Engajamento qualificado da sub-aba NSM não diz se o governador está acima ou abaixo do
   restante do grupo. Em "Todos", a média é puxada por poucos perfis (o líder fica em 100 na escala min-máx
   e comprime os demais).
2. Os dois rankings da sub-aba NSM mostravam só o Top 10 mais o governador selecionado.
3. O comparativo ▲/▼ do Engage no Funil ficava oculto enquanto o máximo de posts de UGC por governador
   fosse 5 ou menos (ADR [0032](0032-funil-em-escala-logaritmica-com-engage-do-ugc-piloto-e-comparativo-vs-mediana.md),
   decisão 4), e o bloco tinha uma linha descritiva.

## Decisão

1. **Comparativo vs. mediana no NSM, em pontos do índice 0-100.** O cartão principal ganha uma seta ao lado
   do valor. Com governador selecionado, é a diferença do valor dele contra a mediana dos DEMAIS perfis com
   NSM (verde acima, vermelha abaixo, sinal e valor sempre em texto, n na legenda). Em "Todos", é a média do
   grupo contra a mediana do grupo, em tom neutro: indica assimetria (poucos perfis altos puxam a média), não
   desempenho. Pontos, e não percentual, porque um percentual sobre um índice min-máx exagera quando a
   mediana é baixa. Não há projeção nem comparação com execuções anteriores. O histórico do NSM não é
   necessário.
2. **Rankings completos com rolagem vertical.** Os dois rankings listam todos os governadores com NSM, em
   contêiner de altura fixa com rolagem. O selecionado continua destacado na posição real. Fica de fora o
   posicionamento automático da rolagem no selecionado: o HTML estático usado hoje não permite.
3. **Engage sempre comparado.** Revisa a decisão 4 do ADR 0032: o ▲/▼ vs. a mediana dos demais aparece
   também com a amostra de teste de UGC, igual às outras etapas, e a linha descritiva do bloco foi removida.
   Com a amostra, a mediana tende a refletir o teto de 5 posts; a decisão é explícita da analista.

## Consequências

- `_ugc_e_amostra_piloto` e o teto `_MAX_POSTS_UGC_PILOTO` foram removidos do módulo do Funil.
- A etiqueta SUBIU/CAIU (posição bruto vs. qualificado) e os cartões de melhor aprovação e maior rejeição não
  mudam; a legenda da seta fala em "mediana dos demais" para não se confundir com SUBIU/CAIU.
- Nenhuma tabela Gold, schema ou pipeline é alterado.
