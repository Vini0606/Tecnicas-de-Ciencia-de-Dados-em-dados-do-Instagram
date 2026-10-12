# Tendência própria

**Status:** em avaliação (fase 1 de 2 concluída)
**Atualizada em:** 2026-10-11

## Pergunta de negócio

"A situação deste governador está melhorando ou piorando?" Substitui as setas do Comparativo vs. mediana, que respondem "quem está
acima dos pares" e não têm eixo de tempo nem noção de incerteza. Escore composto e SUBIU/CAIU permanecem como estão.

## Dados e série

- Série **bruta por data de publicação** do próprio governador, nunca o índice normalizado entre perfis (que misturaria o
  governador com os demais).
- Indicadores previstos: engajamento qualificado (NSM) e as etapas do Funil, na visão por governador e na visão "Todos" (tendência
  do conjunto).
- Limite atual: o piloto tem ~17 reels por perfil espalhados em 21 meses (teto de 30 itens); só a Coleta de 90 dias (#256)
  permite validar.

## Contrato

Quatro estados: **Subindo**, **Caindo**, **Estável**, **Dados insuficientes**. Subindo/Caindo exigem que o intervalo de confiança
exclua zero **e** que a variação estimada passe de `MIN_EFEITO` (ponto de partida: 5% do nível do próprio governador). Sem dado
suficiente, nenhuma seta. Limiares a calibrar na fase 2.

## Método escolhido

Ainda não decidido. **Candidato favorito após a fase 1:** regressão linear do log do valor no tempo, com o formato do conteúdo
como controle (OLS com controles), IC de 95%.

## Alternativas avaliadas (fase 1: simulação, `notebooks/modelagens/tendencia_01_simulacao.ipynb`)

26 perfis × 20 repetições por célula; cenários `base`, `viral` (4% de posts virais) e `mix` (mudança de participação entre
formatos sem efeito real). Números gerais (todos os cenários e tamanhos):

| Método | Falso alarme | Poder | Direção errada | Cobertura do IC | Observação |
|---|---|---|---|---|---|
| OLS com controles | 4,3% | 18% | 0,7% | 95,3% | Calibrado em todos os cenários. Favorito. |
| OLS simples | 14,6% | 20% | 2,6% | 84,8% | 34% de falso alarme no cenário `mix`. |
| Theil–Sen | 14,6% | 20% | 2,5% | 84,9% | Igual ao OLS; a robustez não ajudou no `viral`. |
| ARIMA semanal | 7,5% | 10% | 1,2% | 92,7% | Calibrado em `base`/`viral`, falha no `mix`; menos poder. |
| Hierárquico (empírico-Bayes) | 11,0% | 15% | 4,9% | 77,9% | Cobertura abaixo do nominal; pior com poucos posts. |
| CUSUM (limiar calibrado) | 12,2% | 14% | 2,2% | n/a | Sem magnitude nem IC; só serve como alerta. |

## Validação

- **Feito:** simulação com verdade conhecida (fase 1).
- **Pendente:** *backtest* em dado real com a Coleta de 90 dias (#256); poder por tamanho de efeito; tendência não linear;
  indicadores em forma de proporção (NSM, % positivo); decisão da agregação na visão "Todos" (resultado inconclusivo na fase 1).
- Checagem de sanidade embutida: ARIMA e OLS recuperam a tendência em série sem ruído (a primeira rodada foi descartada por um
  bug de deriva no ARIMA).

## Limitações

- **Poder baixo:** o melhor método detecta ~19% das variações reais de ±15%/±30% com 100 publicações (38% com 250). A maioria das
  setas será "Estável", que no produto deve ser lido como "sem evidência suficiente", não como "nada mudou".
- O gerador assume ruído log-normal, tendência log-linear e efeito constante; o dado real pode violar isso.
- Controlar o formato exige que o formato esteja disponível na série; indicadores sem esse atributo precisam de outro controle.

## Vínculos

- Código: ainda não implementado (candidatos futuros em `dashboard/core/deltas.py` ou `src/modeling/`).
- ADR: [0040](../adr/0040-tendencia-propria-substitui-comparativo-vs-mediana-e-catalogo-de-modelagens.md) (proposto)
- Notebooks: [`notebooks/modelagens/tendencia_01_simulacao.ipynb`](../../notebooks/modelagens/tendencia_01_simulacao.ipynb)
- Glossário: **Tendência** e **Comparativo vs. mediana** em `CONTEXT.md`
- TCC (capítulo/seção): a preencher
