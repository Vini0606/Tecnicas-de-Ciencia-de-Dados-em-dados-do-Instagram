---
status: accepted
---

# Consistência estimada por regressão por publicação, e Tendência do engajamento no Scorecard

## Contexto

A dimensão **Consistência** do Escore composto (ADR
[0030](0030-escore-composto-scorecard-com-consistencia-por-cmgr-de-engajamento-por-data-de-publicacao.md)) era o CMGR de
engajamento por data de publicação: regressão log-linear sobre a **média mensal** de engajamento por post, com mês válido só a
partir de 3 posts maduros e um mínimo de **4 meses válidos** (`MIN_MESES_VALIDOS`), dentro de uma janela de 12 meses completos.

A Coleta do TCC (ver `docs/agents/coletas.md`) cobre **71 dias** (16/08 a 25/10/2026, inclusive). Isso dá, no máximo, **3 meses
elegíveis** (agosto parcial, setembro, outubro parcial) para qualquer perfil, e a regra dos 4 meses deixava a Consistência
**pendente nos 26 perfis**: o escore vigente usava só 4 dimensões, exatamente como no piloto de 2026-10-04 descrito na própria ADR
0030. A regra não vai se resolver sozinha, porque não haverá Coleta mais longa antes da entrega.

A mesma Coleta tem, porém, cerca de **8,5 mil publicações** (reels e posts de feed) com data de publicação. A ficha de modelagem
[`docs/modelagens/tendencia.md`](../modelagens/tendencia.md) e a ADR
[0040](0040-tendencia-propria-substitui-comparativo-vs-mediana-e-catalogo-de-modelagens.md) já haviam avaliado, por simulação com
verdade conhecida, estimadores de tendência que usam a **publicação** como unidade em vez da média mensal. O único método
calibrado em todos os cenários foi a regressão do log do engajamento no tempo com o formato (reel/post) como controle, "OLS com
controles": falso alarme de 4,3%, cobertura do IC de 95% em 95,3%, direção errada em 0,7%. Ele tem intervalo de confiança, controla a
mudança de mistura de formato (que gerava 34% de falso alarme no OLS simples) e funciona com dezenas de pontos por perfil, não com
3 ou 4.

## Decisão

A Consistência passa a ser a **taxa mensal de variação do engajamento por publicação, estimada por regressão sobre as publicações
do próprio governador**. A mesma estimativa alimenta a **Tendência do engajamento**, que entra no Scorecard com os quatro estados
do verbete **Tendência** do `CONTEXT.md`. Especificação fechada com o dono do projeto em 2026-11-18:

1. **Unidade.** Uma publicação: reel de `reels_clean` ou post de `posts_clean`, deduplicada por `id` (um reel também aparece no
   scraper de posts; a linha de reel é a preferida), sem publicações fixadas (`isPinned`, ADR
   [0041](0041-filtro-de-periodo-unico-e-exclusao-de-publicacoes-fixadas.md)) e com pelo menos 7 dias de vida na data de
   referência (`MIN_DIAS_DE_VIDA = 7`, mantido: publicações novas ainda acumulam curtidas).
2. **Modelo.** `log(curtidas + comentários)`, com piso 1, regredido em `t` = dias desde a primeira publicação do perfil
   dividido por 30, mais a variável `formato` (reel = 1, post = 0) como controle, **só quando o perfil tem os dois formatos**.
   β é a taxa logarítmica mensal; **taxa mensal = exp(β) − 1**; IC de 95% = `exp(limites) − 1`. Seguidores ficam fora
   (constantes no perfil).
3. **Confiável.** Pelo menos `MIN_PUBLICACOES = 15` publicações em pelo menos `MIN_DIAS_DISTINTOS = 10` dias distintos. Abaixo
   disso a dimensão fica pendente (`consistencia_pendente = True`) e o escore renormaliza para 4 dimensões, como já fazia
   (`MIN_DIMENSOES_PARA_ESCORE` mantido).
4. **Valor no scorecard.** A taxa mensal estimada, normalizada min-máx entre perfis com a mesma função das outras quatro dimensões.
5. **Tendência (estado).** `"Dados insuficientes"` se não confiável; `"Subindo"` se o limite inferior do IC > 0 **e** taxa
   ≥ +0,05; `"Caindo"` se o limite superior < 0 **e** taxa ≤ −0,05; `"Estável"` caso contrário (`MIN_EFEITO_MENSAL = 0.05`).
6. **Colunas de `governor_scorecard`.** Novas: `consistencia_taxa_mensal`, `consistencia_ic_inferior`,
   `consistencia_ic_superior`, `consistencia_n_publicacoes`, `consistencia_n_dias`, `tendencia_engajamento`;
   `consistencia_pendente` continua. Removida: `consistencia_n_meses` (a única coluna do método antigo além de `consistencia`;
   o scorecard nunca gravou colunas `cmgr_*`). `governor_growth_metrics` (CMGR de audiência, `src/modeling/growth_history.py`)
   **não muda**.
7. **Função pública pura** para notebooks: `estimar_tendencia_engajamento(df_publicacoes, now)` em
   `src/modeling/governor_scorecard.py` (DataFrame de publicações de um perfil → dict com taxa, IC, n, dias, confiável, estado).

**Escopo do dashboard:** só a sub-aba Scorecard. A célula da Consistência mostra o valor normalizado quando confiável e, ao lado,
um selo com o estado da Tendência e a taxa mensal com o IC em texto curto ("+3,2% ao mês, IC 95% de +1,0% a +5,4%"); pendente
continua "pendente", com o selo "Dados insuficientes". Rótulos de usuário: "Consistência" e "Tendência do engajamento"; nunca
"CMGR" nem "OLS" na interface. **NSM, Funil e a visão "Todos" não mudam**: continuam com o Comparativo vs. mediana, e a
Tendência nessas telas, assim como o estimador de proporção, segue em avaliação (ADR 0040).

## Consequências

- A Consistência deixa de ser pendente por construção na Coleta do TCC: perfis com 15 publicações em 10 dias distintos têm valor,
  IC e estado; o escore volta a ter 5 dimensões onde isso vale (peso 0,20) e 4 onde não vale (0,25).
- O significado da dimensão fica mais preciso: tendência do engajamento **por publicação** do próprio governador ao longo do
  tempo, com incerteza. Continua **não** sendo crescimento de audiência (ADR 0030), e o selo de confiabilidade segue dizendo isso.
- A Tendência estreia em produção **só no Scorecard** e **só para contagem** (engajamento por publicação). Isso é um avanço
  parcial da ADR 0040, que permanece proposta para NSM, Funil, "Todos" e proporções; o *backtest* com dado real previsto nela
  continua pendente, e os limiares (15 publicações, 10 dias, 5%) são os pontos de partida da ficha, não valores calibrados.
- Poder baixo (ficha de tendência: ~18 a 20% para efeitos moderados): a maioria dos selos será "Estável", que deve ser lido como
  "sem evidência suficiente de variação", não como "nada mudou". A legenda da sub-aba diz isso.
- O método devolve a melhor reta, não a história: campanha ou sazonalidade dentro dos 71 dias podem gerar seta enganosa (ADR 0040).
  O escore não exibe a série; é uma limitação registrada, a rever se a Tendência for para outras telas.
- O dicionário de dados (`scripts/generate_data_dictionary.py`) e o schema Gold (`GOLD_GOVERNOR_SCORECARD_SCHEMA`) mudam junto;
  uma tabela `governor_scorecard` gravada com o schema antigo precisa ser regerada (`scripts/run_governor_scorecard.py`).
- Reverter exige recalcular a tabela e reexplicar o ranking, por isso o registro.

## Alternativas descartadas

- **Baixar o mínimo de 4 para 3 ou 2 meses válidos.** Com 2 pontos a reta passa sempre pelos dois (a taxa é só a razão entre duas
  médias); com 3 pontos ainda não há incerteza utilizável, e a média mensal joga fora a variação entre publicações que é
  justamente o que dá o IC. Além disso agosto e outubro são meses parciais na Coleta do TCC.
- **Manter 4 meses e declarar a Consistência pendente.** Honesto, mas deixaria o Escore composto com 4 dimensões em toda a
  entrega do TCC, embora haja ~8,5 mil publicações com data para estimar a tendência.
- **OLS simples, Theil–Sen, ARIMA semanal, hierárquico ou CUSUM.** Avaliados na ficha de tendência; todos ficaram descalibrados
  em pelo menos um cenário (ou sem IC, no caso do CUSUM). O controle de formato pesou mais do que a robustez do estimador.
- **Levar a Tendência já para NSM, Funil e "Todos".** Exigiria o estimador de proporção e a regra de agregação do conjunto, ambos
  ainda em avaliação (ADR 0040, fase 2a); o Scorecard é o lugar onde o estimador de contagem já responde à pergunta de negócio.

> Nota (2026-11-19): a janela da Coleta do TCC tem 71 dias inclusivos (16/08 a 25/10/2026); versões anteriores desta ADR diziam 70. Corrigido junto com o texto do TCC (PR `docs-tcc-latex-pretextuais`).
