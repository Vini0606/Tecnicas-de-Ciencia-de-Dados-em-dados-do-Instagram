---
status: accepted
---

# Regressão de performance-por-post (Fase 3 do relatório VHL), separada por formato vídeo/estático, com Lasso, BERTopic de caption e persistência em Gold

## Contexto

A ADR [0018](0018-realinhar-engajamento-e-matriz-de-quadrantes-ao-relatorio-vhl-sem-produto-deputados.md)
corrigiu a métrica de engajamento e adicionou a matriz de quadrantes ao dashboard de governadores,
mas deixou explicitamente fora de escopo a "Fase 3" do relatório estratégico da VHL
(`VHL_Plano_de_Acao_Reconstrucao_Tese_Vendas.docx`): uma regressão nova que, controlando por
alcance, identifica quais preditores (formato, tema, duração, horário, frequência, patrocínio)
preveem engajamento — com teste de circularidade e validação fora da amostra. A ADR 0018 registrou
duas perguntas em aberto para quando essa frente entrasse: (1) a métrica de engajamento daquela ADR
reconcilia ou coexiste com o que a regressão nova produzir? (2) a regressão roda como análise
pontual ou vira estágio de pipeline? Esta ADR é onde essas duas perguntas se resolvem, via nova
rodada de `/grilling`.

Investigação de código nesta sessão (antes do grilling) confirmou pontos que mudaram o desenho:

- **A regressão "furada" que o relatório da VHL critica já existe neste repositório**, em
  `notebooks/04_analise_regressao.ipynb`: `X = df_reels[['videoPlayCount']]` (um único preditor),
  `Y = likesCount`, nível de reel (não post agregado, não perfil), outliers cortados por z-score,
  um único `train_test_split(test_size=0.2)` sem teste de circularidade formal. Fase 3 não é
  trabalho do zero — é substituir/consertar algo que já está na TCC. Nenhum outro código de
  regressão existe no repositório (`grep` por `LinearRegression`/`sklearn.linear_model`/
  `statsmodels` só encontra esse notebook).
- **Um segundo problema de validação, além da circularidade que a VHL já aponta**: o
  `train_test_split` do notebook é por post individual, não por governador. Como cada governador
  tem vários posts, isso vaza identidade de perfil entre treino e teste — o modelo pode aprender a
  reconhecer o governador em vez de aprender o preditor de verdade, inflando o R² sem generalização
  real.
- **Disponibilidade real de dados por preditor** (`src/schemas_delta.py`,
  `src/features/silver/post_cleaner.py`): `videoPlayCount`/`videoDuration` existem para posts e
  reels; `caption` sobrevive ao Silver, mas `hashtags` está em `PostCleaner.POSTS_COLUMNS_TO_DROP`
  (descartado no Bronze→Silver); nenhum schema tem campo de `transcript` (mesmo gap de shares/
  salvamentos já registrado na ADR 0018); `isSponsored` (proxy de `paidPartnership`) só existe em
  `BRONZE`/`SILVER_REELS_SCHEMA`, não em posts; o campo bruto `type` do Apify (que traria
  imagem/carrossel/vídeo) chega ao Bronze mas o `PostCleaner` sobrescreve tudo com `Tipo` =
  `FEED`/`REELS`, perdendo essa granularidade antes do Silver; `FREQUENCIA` já existe em
  `governor_engagement` (Gold), mas por perfil/execução inteira, não por post individual; posts
  estáticos (imagem/carrossel) não têm métrica de alcance exposta pela plataforma — só vídeo tem
  `videoPlayCount` — limite que o próprio relatório da VHL reconhece.
- **BERTopic já existe no projeto, mas roda sobre comentários**, não sobre captions de post — é uma
  frente de NLP formalmente distinta da modelagem de performance-por-post que a Fase 3 pede.
- **Amostra pequena**: 27 governadores, não os 254 deputados que o relatório da VHL tinha em mente
  ao sugerir "treinar em ~200 perfis, testar nos 54 restantes" — essa proporção precisa ser
  repensada para uma base bem menor.

## Decisão

1. **Escopo cobre todos os formatos de post desta vez** (feed + reels), não só reels.
2. **Duas regressões separadas, por grupo de formato** — não uma regressão única com formato como
   preditor categórico:
   - Grupo **vídeo** = tabela `reels_clean` (Silver Reels) inteira. Controla por `videoPlayCount`
     (alcance).
   - Grupo **estático** = tabela `posts_clean` (Silver Posts) inteira. Controla só por
     `followersCount` (sem alcance — a plataforma não expõe isso para imagem/carrossel).
   - O agrupamento é **por tabela de origem**, não por valor do campo `type` — um post do feed
     eventualmente marcado como vídeo continua no grupo estático. `type` vira preditor descritivo
     *dentro* de cada grupo, não critério de qual grupo o registro entra.
3. **Variável-alvo (Y) reconciliada com a ADR 0018**: `(likesCount + commentsCount × Wc) /
   followersCount`, calculada por **post individual** (não por perfil agregado), reaproveitando o
   mesmo `Wc` que `EngagementAggregator` já calibra por execução. Uma única definição de
   "engajamento honesto" no projeto inteiro.
4. **Preditores**:
   - **Formato**: campo bruto `type` do Apify (Bronze), restaurado como coluna nova no Silver — sem
     re-scraping, o dado já existe, só nunca sobreviveu ao `PostCleaner`. `Tipo` (`FEED`/`REELS`)
     continua existindo sem mudança, para não quebrar consumidores atuais.
   - **Tema/pauta**: BERTopic de verdade sobre `caption` + `hashtags` (também restaurado no
     Silver, mesma lógica de dado já coletado e descartado) — análogo ao BERTopic que já roda sobre
     comentários, mas um modelo novo e distinto, sobre um corpus diferente (captions de post, não
     comentários).
   - Duração do vídeo (`videoDuration`, nulo para imagem estática por natureza), comprimento de
     legenda (derivado de `caption`), horário e dia da semana (derivados de `data_hora`),
     `FREQUENCIA` (Gold, por perfil).
   - `paidPartnership` (via `isSponsored`) — só existe no grupo vídeo (Reels); o grupo estático
     fica sem esse preditor por ausência de dado, não por escolha de design.
5. **Divisão treino/teste por governador** (holdout de perfis inteiros — todos os posts de um
   governador do conjunto de teste ficam fora do treino), não por post individual, para eliminar o
   vazamento de identidade de perfil identificado nesta sessão. Substitui a proporção "~200/54" do
   relatório da VHL (pensada para 254 deputados) por algo equivalente para 27 governadores (ex.:
   ~20/7, ou k-fold por governador dado o N pequeno).
6. **Tipo de modelo**: regressão linear regularizada (**Lasso**), não OLS simples — com dummies de
   tópico (BERTopic) somados aos demais preditores sobre uma amostra pequena, o risco de
   overfitting de uma regressão linear simples é real. Lasso mantém coeficientes interpretáveis
   ("peso estimado" por driver, como o relatório da VHL pede) e já filtra preditores fracos.
7. **Teste de circularidade vira checagem automática em código**, não só documentação: antes de
   rodar a regressão, uma função valida que nenhum preditor é derivado das mesmas colunas brutas
   que compõem Y (`likesCount`/`commentsCount`), mais um alerta/erro se a correlação bruta entre
   preditor e Y passar de um limiar alto (ex. > 0.95). Falha alto e cedo — não deixa a regressão
   rodar sobre um desenho circular.
8. **Onde vive**: estágio novo **dentro da orquestração automática existente**
   (`src/modeling/orchestration.py`, que já roda PCA → clustering → sentimento → tópicos), não um
   script separado como `scripts/run_profile_clustering_engagement.py`.
9. **O que persiste em Gold**: duas coisas, para cada grupo (vídeo/estático) e cada execução —
   coeficientes + R² de treino/holdout (tabela pequena, um resumo do modelo), **e** previsão +
   resíduo por post (tabela maior, granularidade de post individual).
10. **Consumo no dashboard já nesta rodada**: página **Performance** (mesma página da matriz de
    quadrantes e comparação com pares, ADR 0017/0018) ganha um card de "lacuna de execução" — o
    resíduo médio do governador selecionado, por grupo (vídeo e estático mostrados separadamente,
    sem inventar uma fórmula de combinar as duas escalas de resíduo) — mais uma lista dos posts com
    maior resíduo positivo/negativo daquele governador.
11. **Dois notebooks novos**, um por grupo (`vídeo` e `estático`), no mesmo espírito acadêmico dos
    notebooks `01`-`05` existentes — cada um roda a regressão correspondente e os testes de
    pressupostos do modelo linear: normalidade dos resíduos (Shapiro-Wilk, como o notebook atual já
    faz), homocedasticidade, independência/autocorrelação dos resíduos (Durbin-Watson, como o
    notebook atual já faz) e multicolinearidade entre preditores (VIF — relevante com dummies de
    tópico no preditor de tema).
12. **`notebooks/04_analise_regressao.ipynb` (a regressão circular) é removido** do repositório,
    substituído pelos dois notebooks novos e pelo estágio de pipeline.

## Por que

- Duas regressões separadas seguem literalmente a recomendação do próprio relatório da VHL ("não
  existe fórmula única de engajamento para todos os formatos") — vídeo e estático têm denominadores
  fisicamente diferentes (alcance vs. só seguidores), misturar os dois numa métrica-alvo comum
  confundiria dois fenômenos.
- Agrupar por tabela de origem, não por valor de `type`, evita ter que unir duas Silver tables com
  schemas diferentes numa base só antes de agrupar — ganho de precisão pequeno (posts de vídeo fora
  de Reels são raros no Instagram atual) não justifica esse custo de engenharia.
- Reconciliar Y com o `Wc` da ADR 0018 evita o mesmo problema que motivou aquela ADR: duas
  definições de "engajamento honesto" coexistindo no projeto, risco de divergência.
- Split por governador (não por post) resolve um vazamento de generalização que existe no notebook
  atual e que o próprio relatório da VHL não menciona explicitamente, mas que compromete qualquer
  validação fora da amostra feita sobre posts sorteados aleatoriamente.
- Lasso em vez de OLS: BERTopic sobre captions provavelmente produz várias colunas dummy de tópico;
  somadas aos demais preditores sobre 27 perfis, uma regressão linear simples arriscaria overfitting
  sério. O relatório da VHL já antecipa que "poucos drivers" é uma resposta válida — Lasso formaliza
  essa possibilidade em vez de forçar todos os preditores a terem peso.
- Circularidade como checagem em código, não só design documentado, evita que uma iteração futura
  reintroduza um preditor circular sem perceber — o próprio erro que motivou todo este trabalho.
- Estágio dentro da orquestração existente e persistência de coeficientes + previsão/resíduo por
  post (não só coeficientes) e consumo já no dashboard: decisão do usuário por escopo mais completo
  nesta rodada, em vez do padrão mais mínimo (análise pontual, só coeficientes, dashboard depois)
  usado nas ADRs anteriores — este relatório documenta a escolha, não substitui o julgamento do
  usuário sobre quanto escopo cabe numa rodada.
- Notebooks de diagnóstico por grupo mantêm o rigor acadêmico que a TCC já tinha (o notebook atual
  já roda Shapiro-Wilk e Durbin-Watson) — a regressão nova não pode ser menos rigorosa
  metodologicamente que a que está sendo substituída, e os pressupostos do modelo linear (mesmo
  regularizado) continuam precisando de verificação explícita, não presumida.
- Remover o notebook antigo segue o mesmo racional da ADR 0013 ("remover pipeline legado e
  artefatos de migração já concluída") — mantê-lo arrisca alguém rodar ou citar a análise circular
  por engano.

## Opções consideradas

- **Escopo só Reels nesta rodada** (onde alcance sempre existe) — rejeitada pelo usuário; escolheu
  cobrir todos os formatos já, aceitando a estrutura de duas regressões separadas como resposta ao
  problema do denominador.
- **Uma regressão única, formato como preditor categórico, sem controle de alcance para ninguém** —
  rejeitada: jogaria fora o sinal de alcance que existe para vídeo, e misturaria duas coisas
  fisicamente diferentes (post visto vs. post exposto a X seguidores) na mesma variável-alvo.
- **Split treino/teste por post individual** (mesmo padrão do notebook atual) — rejeitada: vazamento
  de identidade de governador entre treino e teste, discutido acima.
- **Não restaurar o campo `type` bruto, usar só `Tipo` (FEED/REELS)** — rejeitada: Formato viraria
  constante dentro de cada uma das duas regressões (grupo vídeo = só reels, grupo estático = só
  posts), deixando de funcionar como preditor.
- **Agrupar vídeo/estático por valor real de `type`** (cruzando as duas Silver tables) — rejeitada:
  mais trabalho de engenharia (unir schemas diferentes) para um ganho de precisão provavelmente
  pequeno.
- **Proxy simples para tema** (comprimento de legenda + contagem de hashtags, sem topic modeling) —
  rejeitada pelo usuário; escolheu BERTopic de verdade sobre captions, mais fiel ao que a VHL pede,
  aceitando o escopo maior (modelo de NLP novo).
- **OLS simples**, mesmo tipo de modelo do notebook atual — rejeitada: risco de overfitting com
  múltiplos preditores (incluindo dummies de tópico) sobre amostra pequena.
- **Circularidade só documentada na ADR, sem checagem em código** — rejeitada pelo usuário; escolheu
  uma checagem automática que falha alto e cedo.
- **Análise pontual, fora do pipeline automático** (recomendação inicial, rejeitada pelo usuário) —
  usuário preferiu estágio persistido em Gold, recalculado a cada execução.
- **Script separado da orquestração** (recomendação inicial, rejeitada pelo usuário) — usuário
  preferiu integrar dentro de `src/modeling/orchestration.py`.
- **Só coeficientes + R² em Gold** (recomendação inicial, rejeitada pelo usuário) — usuário quis
  também previsão/resíduo por post, para já habilitar a "lacuna de execução" no dashboard.
- **Consumo no dashboard como spec separada, depois** (recomendação inicial, rejeitada pelo
  usuário) — usuário quis o card de lacuna de execução já nesta mesma rodada.
- **Manter o notebook antigo como histórico** — rejeitada pelo usuário; escolheu remover.

## Consequências

- **Não implementado nesta sessão ainda** — esta ADR registra a decisão de escopo e desenho; a
  implementação (restaurar `type`/`hashtags` no Silver, BERTopic de caption, checagem de
  circularidade, os dois modelos Lasso, integração em `orchestration.py`, schemas Gold novos, card
  de lacuna de execução em Performance, os dois notebooks de diagnóstico, remoção do notebook
  antigo) fica para uma spec/issue futura (`/to-spec` → `/implement` → `/code-review`), mesmo padrão
  já validado nas rodadas anteriores.
- É uma rodada de escopo bem maior que a ADR 0018: dois modelos de regressão, um pipeline de NLP
  novo (BERTopic sobre captions), duas tabelas Gold novas por grupo, uma checagem de circularidade
  reutilizável, dois notebooks de diagnóstico, e uma feature nova de dashboard — vale considerar
  quebrar a implementação em specs/issues menores e sequenciais em vez de uma só monolítica, mesmo
  raciocínio de "commits pequenos e seguros" já usado no projeto.
- O grupo estático fica permanentemente sem preditor de alcance e sem `paidPartnership` — qualquer
  leitura dos coeficientes desse modelo precisa comunicar essa limitação, não é um gap temporário.
- `hashtags` e o campo bruto `type` passam a ser colunas Silver de verdade — qualquer consumidor
  futuro de `posts_clean` herda essas colunas; nada quebra hoje porque nada mais depende delas
  ainda, mas o schema Silver de posts cresce.
- A checagem de circularidade em código vira uma responsabilidade permanente: qualquer preditor novo
  adicionado no futuro (a este ou a outro modelo do projeto) precisa passar por ela, não só por
  revisão humana.
- O notebook `04_analise_regressao.ipynb` deixa de existir — qualquer referência externa a ele
  (documentação, handoffs anteriores) fica desatualizada; os dois notebooks novos assumem esse
  papel.
- O card de "lacuna de execução" em Performance depende de as duas regressões já terem rodado pelo
  menos uma vez (Gold populado) — mesma degradação graciosa que o resto do dashboard já pratica
  quando uma tabela ainda não existe.
