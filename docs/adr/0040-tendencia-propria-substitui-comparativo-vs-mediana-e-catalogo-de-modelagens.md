---
status: proposed
---

# Tendência própria substitui o Comparativo vs. mediana, e as modelagens passam a ter catálogo e avaliação por simulação

## Contexto

O Comparativo vs. mediana (ADR 0032 e 0033) mostra uma seta ▲/▼ comparando o governador com a mediana dos demais. Ela tem três
limites:

- Não tem eixo de tempo: responde "quem está acima dos pares", não "a situação está melhorando ou piorando".
- A seta aparece sempre que há dois números, mesmo para diferenças pequenas, sem noção de incerteza.
- No NSM, o índice exibido é min-máx **entre os perfis**; qualquer variação calculada sobre ele mistura o governador com os
  demais.

Além disso, a evidência das modelagens do projeto está espalhada entre notebooks narrativos (`01`-`07`), notebooks de diagnóstico
de tabela (ADR 0022), ADRs e código. Nada reúne, para cada modelagem, a pergunta, o método, as alternativas avaliadas, a
validação e a seção do TCC.

A Silver do piloto não permite escolher um método: tem ~17 reels por perfil espalhados em 21 meses. A Coleta de 90 dias (#256)
ainda não foi feita.

## Decisão

- **A Tendência substitui as setas do Comparativo vs. mediana.** Calculada sobre a série **bruta por data de publicação**, nunca
  sobre o índice normalizado entre perfis.
- **Quatro estados**: Subindo, Caindo, Estável, Dados insuficientes. Subindo/Caindo exigem que o intervalo de confiança da
  variação exclua zero **e** que a variação estimada passe de um tamanho mínimo (ponto de partida: 5% do nível do próprio
  governador). Sem dado suficiente, nenhuma seta. Os limiares são parâmetros a calibrar, não números fixados aqui.
- **Visão "Todos"**: tendência do **conjunto** (série agregada), com o mesmo contrato. A forma de agregar é decidida na avaliação,
  porque um perfil que publica muito pode dominar a série.
- **Mantidos como estão**: SUBIU/CAIU (posição no ranking) e o Escore composto (relativo entre pares, ADR 0030).
- **Catálogo de modelagens** em `docs/modelagens/`: uma ficha por modelagem (pergunta, dados, método, alternativas, validação,
  limitações, status, links para código, ADR, notebook e TCC). Todas as modelagens existentes entram no inventário; as fichas
  são preenchidas aos poucos.
- **Notebooks de avaliação** em `notebooks/modelagens/`, separados da narrativa do TCC (`01`-`07`) e do diagnóstico de tabela
  (`diagnostico_medallion/`, ADR 0022).
- **Avaliação em duas fases**: primeiro simulação com verdade conhecida (falso alarme, poder, direção errada, cobertura do IC,
  sensibilidade a perfil dominante e a post viral, confusão com mudança de mix de formato); depois *backtest* com a Coleta de
  90 dias. A escolha do método e a mudança no dashboard só acontecem depois da segunda fase.

## Consequências

- O Comparativo vs. mediana continua valendo na interface até a Tendência ser validada e implementada; o `CONTEXT.md` registra a
  substituição como em andamento.
- Esta ADR fica **proposta** até a fase de dado real. Quando o método for escolhido, ela é atualizada (ou uma ADR nova a
  referencia) com o método, os limiares calibrados e o desenho final das setas.
- **Resultado preliminar da fase 1** (`notebooks/modelagens/tendencia_01_simulacao.ipynb`, ficha `docs/modelagens/tendencia.md`):
  a regressão do log do valor no tempo com o formato como controle foi o único método calibrado em todos os cenários (falso
  alarme 4,3%, cobertura do IC 95,3%). Controlar a mudança de mix de formato pesou mais que usar estimador robusto. O poder é
  baixo (~19% com 100 publicações), então a maioria das setas será "Estável", e a interface deve dizer "sem evidência
  suficiente". Isso não fixa o método: falta o *backtest* com dado real.
- O filtro de período para publicações não fixadas é uma trilha separada, sem dependência desta decisão.
- A simulação mede o comportamento dos métodos sob as premissas do gerador; não prova que o Instagram real se comporta assim.
  Por isso o *backtest* com dado real é obrigatório antes de produção.

## Alternativas descartadas

- **Manter a seta binária e só mostrar a inclinação**: mais simples, mas reproduz o falso sinal por ruído.
- **Substituir também o Escore composto**: descartado pelo autor; ele continua relativo entre pares.
- **Esperar a Coleta final para começar a avaliar**: adiaria a escolha e deixaria a Coleta de ~US$ 37,82 dependente de uma
  decisão de modelagem ainda aberta.
