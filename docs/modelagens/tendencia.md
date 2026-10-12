# Tendência própria

**Status:** em avaliação (fases 1 e 2a de simulação concluídas; falta o *backtest* com dado real)
**Atualizada em:** 2026-10-11

## Pergunta de negócio

"A situação deste governador está melhorando ou piorando?" Substitui as setas do Comparativo vs. mediana, que respondem "quem está
acima dos pares" e não têm eixo de tempo nem noção de incerteza. Escore composto e SUBIU/CAIU permanecem como estão.

## Dados e série

- Série **bruta por data de publicação** do próprio governador, nunca o índice normalizado entre perfis (que misturaria o
  governador com os demais).
- Indicadores previstos: engajamento qualificado (NSM) e as etapas do Funil, na visão por governador e na visão "Todos" (tendência
  do conjunto). Dois tipos de indicador: **contagem** (engajamento por post) e **proporção** (engajamento qualificado, % positivo
  e % negativo de comentários, com número de comentários variável por data).
- Limite atual: o piloto tem ~17 reels por perfil espalhados em 21 meses (teto de 30 itens); só a Coleta de 90 dias (#256)
  permite validar.

## Contrato

Quatro estados: **Subindo**, **Caindo**, **Estável**, **Dados insuficientes**. Subindo/Caindo exigem que o intervalo de confiança
exclua zero **e** que a variação estimada passe de `MIN_EFEITO` (ponto de partida: 5% do nível do próprio governador). Sem dado
suficiente, nenhuma seta. Limiares a calibrar no *backtest* (faixas sugeridas abaixo).

## Método escolhido

Ainda não decidido. Candidatos após as fases 1 e 2a (simulação):

- **Indicadores de contagem:** regressão linear do log do valor no tempo, com o formato do conteúdo como controle (OLS com
  controles), IC de 95%.
- **Indicadores de proporção:** o mesmo OLS, aplicado ao log da proporção com correção de continuidade
  (`log((k+0,5)/(n+1))` por publicação, sem peso, com formato como controle). Alternativa equivalente: meta-regressão no logit
  empírico por post (efeitos aleatórios, Knapp–Hartung), a considerar se houver muitas publicações com poucos comentários.
- **Visão "Todos" (regra provisória):** cada perfil pesa igual, nunca soma bruta. Implementação preferida: **mediana das tendências
  individuais** com IC por *bootstrap* de perfis. Alternativa de mais poder em contagem: valores normalizados pelo nível do perfil
  e cada post ponderado por 1/n do perfil.
- **Faixa de limiares a testar no *backtest*:** `MIN_EFEITO` de 2% a 10% (a simulação não distingue esses valores);
  `MIN_PUBLICACOES` de 10 a 20; `MIN_DIAS_COM_PUBLICACAO` de 8 a 15.

## Alternativas avaliadas

Fase 1 (`tendencia_01_simulacao.ipynb`): 26 perfis × 20 repetições por célula; cenários `base`, `viral` (4% de posts virais) e
`mix` (mudança de participação entre formatos sem efeito real). Contagem, números gerais:

| Método | Falso alarme | Poder | Direção errada | Cobertura do IC | Observação |
|---|---|---|---|---|---|
| OLS com controles | 4,3% | 18% | 0,7% | 95,3% | Calibrado em todos os cenários. Favorito. |
| OLS simples | 14,6% | 20% | 2,6% | 84,8% | 34% de falso alarme no cenário `mix`. |
| Theil–Sen | 14,6% | 20% | 2,5% | 84,9% | Igual ao OLS; a robustez não ajudou no `viral`. |
| ARIMA semanal | 7,5% | 10% | 1,2% | 92,7% | Calibrado em `base`/`viral`, falha no `mix`; menos poder. |
| Hierárquico (empírico-Bayes) | 11,0% | 15% | 4,9% | 77,9% | Cobertura abaixo do nominal; pior com poucos posts. |
| CUSUM (limiar calibrado) | 12,2% | 14% | 2,2% | n/a | Sem magnitude nem IC; só serve como alerta. |

Fase 2a (`tendencia_02_proporcoes_e_agregacao.ipynb`), **proporção**: 200 repetições × 26 perfis por célula, quatro cenários
(`base`, `viral` com post de 15× comentários e sentimento atípico, `mix`, `poucos` comentários) e 20/60/150 publicações. Totais,
com erro de Monte Carlo (± 1 e.p.):

| Método | Falso alarme | Poder | Direção errada | Cobertura do IC | Observação |
|---|---|---|---|---|---|
| OLS do log da proporção (`ols_ref`) | 4,9 ± 0,1% | 21,5 ± 0,2% | 0,4% | 94,7 ± 0,1% | Único calibrado em todos os cenários (pior caso 5,2% e 94,5%). Candidato. |
| Meta-regressão logit (`meta_regressao_logit`) | 4,6% | 19,9% | 0,4% | 95,3% | Equivalente; falso alarme 6,6% com poucos comentários. |
| Peso limitado + erro robusto (`cap_robusto`) | 7,1% | 23,7% | 0,7% | 92,8% | Calibração no limite (7,7% / 92,3% no pior caso). |
| Quase-binomial ponderada por comentários | 25,8% | 30,1% | 5,9% | 74,2% | Descalibrada; no `viral`, 37,9% de falso alarme. |
| Quase-binomial com erro robusto | 13,8% | 22,3% | 2,5% | 86,2% | Melhora, mas continua descalibrada. |
| Binomial sem correção de sobredispersão | 49,5% | 46,0% | 12,6% | 50,4% | Super-confiante. |
| Proporção por janela com Wilson | 55,1% | 43,6% | 16,5% | 45,0% | Supõe comentários independentes; não controla formato. |

Fase 2a, **agregação em "Todos"** (um perfil dominante com nível ×D, 3× mais publicações; D = 1, 10, 30, 100; 250 repetições por
célula; verdade = média dos efeitos com peso igual por perfil). Acerto do estado do conjunto, todas as células:

| Agregação | Contagem | Proporção | Observação |
|---|---|---|---|
| Soma bruta | 34,1% | 32,9% | Dominante manda; com D = 100 a proporção erra a direção em 29% das repetições (cenário C). |
| Normalizada por perfil | 81,0% | 68,5% | Em contagem o perfil que publica mais ainda pesa mais (viés). |
| Normalizada, peso igual por perfil | 93,9% | n/d | Mais poder em contagem; sem direção errada. |
| Mediana das tendências | 85,7% | 96,0% | Nunca errou a direção. Regra provisória. |
| Meta-análise de efeitos aleatórios | 84,9% | 92,6% | Pende para o perfil mais preciso (às vezes o dominante). |

## Validação

- **Feito (fase 1):** simulação com verdade conhecida para contagem.
- **Feito (fase 2a):** proporções, poder por tamanho de efeito, sensibilidade a limiares, agregação em "Todos" com dominância forte
  e tendência não linear, todos com erro de Monte Carlo informado. Checagens de sanidade com asserção: implementações batem com
  `statsmodels`, métodos recuperam a variação em série sem ruído, e em binomial pura (sem sobredispersão) o quase-binomial e a
  meta-regressão têm cobertura de 95,5% e 97,0%.
- **Poder por efeito** (250 publicações; 100 entre parênteses): queda de 30% detectada em 84% (49%) na contagem e 89% (56%) na
  proporção; alta de 30% em 59% (29%) e 82% (53%); efeitos de ±10% ficam em 12 a 24% mesmo com 250 publicações. **Efeito mínimo
  detectável a 80%** com 250 publicações: 28,8% (queda) e 42,9% (alta) em contagem; 26,5% e 29,3% em proporção. Com 50 publicações
  ou menos nenhum chega a 80% até ±50%.
- **Sensibilidade:** `MIN_EFEITO` de 0 a 15% dá resultados idênticos (o IC excluir zero já exige variação grande). Subir os
  mínimos de publicações/dias de `(10, 8)` para `(20, 15)` aumenta "Dados insuficientes" de ~10% para ~32% e baixa o falso alarme
  de ~4,2% para 3,1%, com ganho de poder entre as séries classificadas de ~2 a 3 pp; o falso alarme já está no nominal.
- **Tendência não linear** (250 publicações, variação ponta a ponta ≈ 0): campanha no início produz "Caindo" em 81,5% das séries;
  campanha no fim produz "Subindo" em 91,8%; sazonalidade de 30 dias produz "Caindo" em 43,7%; campanha no meio fica "Estável".
  Um degrau permanente de +30% é estimado em +46%. O sinalizador de não linearidade (termo quadrático) só pega a campanha no meio.
- **Pendente:** *backtest* em dado real com a Coleta de 90 dias (#256); autocorrelação e eventos comuns a todos os perfis;
  mais de um perfil dominante.
- O teste de fumaça com a Silver do piloto (24 de 25 perfis "Dados insuficientes") só confirma que o código roda; não escolhe
  método.

## Limitações

- **Poder baixo:** só variações da ordem de ±30% são detectadas com frequência razoável (com 250 publicações). A maioria das
  setas será "Estável", que no produto deve ser lido como "sem evidência suficiente", não como "nada mudou". Mostrar magnitude e
  incerteza junto da seta.
- **Tendência não linear:** o método devolve a melhor reta, não a história. Campanha e sazonalidade geram seta enganosa; a
  interface precisa mostrar a série junto da seta, e o sinalizador quadrático não é suficiente.
- O gerador assume ruído log-normal (contagem) ou logit-normal entre posts (proporção), tendência log/logit-linear e efeito
  constante, número de comentários independente da proporção e do tempo, publicações sem autocorrelação e perfis independentes. O
  dado real pode violar qualquer uma.
- A regra de agregação foi testada com **um** perfil dominante e efeitos homogêneos nos demais.
- A escolha do candidato de proporção usa limites de calibração que foram endurecidos depois de ver a primeira rodada
  (registrado no notebook); com os limites originais venceria `cap_robusto`.
- Controlar o formato exige que o formato esteja disponível na série; indicadores sem esse atributo precisam de outro controle.

## Vínculos

- Código: ainda não implementado (candidatos futuros em `dashboard/core/deltas.py` ou `src/modeling/`).
- ADR: [0040](../adr/0040-tendencia-propria-substitui-comparativo-vs-mediana-e-catalogo-de-modelagens.md) (proposto)
- Notebooks: [`notebooks/modelagens/tendencia_01_simulacao.ipynb`](../../notebooks/modelagens/tendencia_01_simulacao.ipynb),
  [`notebooks/modelagens/tendencia_02_proporcoes_e_agregacao.ipynb`](../../notebooks/modelagens/tendencia_02_proporcoes_e_agregacao.ipynb)
- Glossário: **Tendência** e **Comparativo vs. mediana** em `CONTEXT.md`
- TCC (capítulo/seção): a preencher
