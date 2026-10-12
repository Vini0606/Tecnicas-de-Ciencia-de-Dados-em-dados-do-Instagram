# Regressão de performance por post (Lasso)

**Status:** a documentar
**Atualizada em:** 2026-10-11

> Justificativa do status: a modelagem está implementada e roda como estágio da orquestração, mas **nenhuma evidência em dado
> real está registrada**. As únicas saídas salvas (notebooks 06 e 07) parecem vir de dado sintético e mostram R² de holdout
> negativo. Não é `validada`; também não é `em avaliação`, porque nenhuma fonte formula a pergunta aberta nem compara métodos.
> Falta rodar e registrar o resultado sobre os governadores reais.

## Pergunta de negócio

Controlando pelo alcance quando ele existe, quais características de um post (formato, tema da legenda, duração, horário, dia
da semana, frequência de postagem do perfil, patrocínio) preveem o engajamento? E qual o "desvio" de cada post em relação ao
esperado (resíduo), que sustentaria uma "lacuna de execução" por governador (ADR 0019, Decisão 10)? Substitui a regressão
circular do antigo `notebooks/04_analise_regressao.ipynb` (visualizações prevendo curtidas, o mesmo fenômeno medido duas vezes),
removido do repositório (ADR 0019, Decisões 11 e 12; ADR 0018, Contexto).

## Dados e série

Duas regressões separadas, por **tabela de origem** e não pelo valor do campo `type` (ADR 0019, Decisão 2):

| Grupo | Tabela Silver | Controle de alcance | Preditores exclusivos |
|---|---|---|---|
| Vídeo | `reels_clean` | `videoPlayCount` | `paidPartnership` (derivado de `isSponsored`) |
| Estático | `posts_clean` (sem os `id` que também estão em `reels_clean`) | nenhum (a plataforma não expõe alcance de imagem/carrossel) | `comprimento_legenda`, `Topic` (BERTopic sobre `caption` + `hashtags`) |

- **Variável-alvo `Y`** por post individual: `(likesCount + commentsCount x Wc) / followersCount`, com o mesmo `Wc` que o
  `EngagementAggregator` calibra a cada execução (`_WC_COMENTARIO`), para haver uma só definição de "engajamento honesto" no
  projeto (ADR 0019, Decisão 3; ADR 0018, Decisão 3). Posts de perfil sem `followersCount` positivo são descartados.
- **Preditores comuns** (`PostPerformanceConfig`, `src/modeling/config.py`): `hora_do_dia`, `FREQUENCIA` (Gold, por perfil),
  `videoDuration`, `tem_duracao`; categóricos `type_raw` (campo bruto `type` do Apify, restaurado no Silver) e `dia_da_semana`.
- Reels não têm `caption` nem `hashtags` no Bronze/Silver, por isso o grupo vídeo não tem Tema nem comprimento de legenda; o
  grupo estático não tem `videoPlayCount` nem `paidPartnership`. Ambas as ausências são estruturais e permanentes, não escolha
  de design (ADR 0019, Consequências; comentários em `config.py`).
- Granularidade: 1 linha por post/reel. Saída em Gold: `post_performance_coefficients` (coeficientes, R² de treino e de
  holdout, tamanhos, `alpha`) e `post_performance_predictions` (previsão e resíduo por post).
- Tamanho real da amostra: não registrado. As saídas salvas de `notebooks/06_regressao_performance_video.ipynb` e `07_...` têm
  300 reels (ou 300 posts) e 15 governadores, com ids no formato `gov0_reel_0` e `inputUrl` `https://instagram.com/gov0`, o que
  indica dado sintético ou de teste, não os 26 a 27 governadores reais (inferência a partir das saídas; os notebooks não
  declaram a origem).

## Método escolhido

Estágio dentro da orquestração (`run_post_performance_stage`, chamado por `run_deterministic_modeling`), com falha isolada
(exceção é registrada e o estágio é pulado sem derrubar os demais; ADR 0019, "dado insuficiente" e `orchestration.py`).

1. **Teste de circularidade em código** (`check_circularity`): erro `CircularityError` se algum preditor for literalmente
   `likesCount`/`commentsCount`, ou se a correlação bruta entre um preditor numérico e `Y` passar de 0,95
   (`circularity_correlation_threshold`). Coluna constante é ignorada.
2. **Divisão treino/teste por governador** (`select_holdout_governors`): `holdout_governors_count=7` governadores inteiros
   fora do treino, com `random_state=42`, o mesmo conjunto nos dois grupos para que os R² de holdout sejam comparáveis. Elimina
   o vazamento de identidade de perfil do `train_test_split` por post do notebook antigo (ADR 0019, Contexto e Decisão 5).
3. **Modelo:** `Pipeline` com `StandardScaler` nos numéricos e `OneHotEncoder` nos categóricos, seguido de `LassoCV` (5 dobras,
   `max_iter=10_000`, `alpha` por validação cruzada). Lasso em vez de OLS por causa do risco de sobreajuste com dummies de tópico
   numa amostra pequena; mantém coeficientes interpretáveis e zera preditores fracos (ADR 0019, Decisão 6).
4. **Tema:** `classify_post_topics` (BERTopic sobre `caption` + `hashtags`, `PostTopicModelConfig`: `nr_topics=15`, HDBSCAN
   5/2), ver [topicos.md](topicos.md). A própria docstring da configuração diz que os valores de `nr_topics` e HDBSCAN ainda
   são "placeholders" a calibrar, não derivados de dados reais.
5. **Diagnóstico de pressupostos** nos notebooks 06 e 07, sobre os resíduos de **holdout**: Shapiro-Wilk, Durbin-Watson,
   Breusch-Pagan e VIF (ADR 0019, Decisão 11).

## Alternativas avaliadas

Registradas na ADR 0019 (Opções consideradas).

| Alternativa | Vantagem | Desvantagem | Resultado |
|---|---|---|---|
| Uma regressão única com formato como preditor categórico | Simples | Joga fora o sinal de alcance dos vídeos e mistura dois denominadores diferentes | Rejeitada; duas regressões |
| Escopo só Reels | Alcance sempre existe | — | Rejeitada pelo autor; cobre feed e reels |
| Divisão treino/teste por post (padrão do notebook antigo) | Simples | Vaza identidade do governador entre treino e teste | Rejeitada; holdout por governador |
| OLS simples | Mesmo modelo do notebook antigo | Risco de sobreajuste com muitos preditores e amostra pequena | Rejeitada; Lasso |
| Agrupar vídeo/estático pelo valor real de `type` | Mais precisão | Obriga a unir duas Silver com schemas diferentes, ganho pequeno | Rejeitada; agrupamento por tabela de origem |
| Proxy simples de tema (comprimento de legenda + contagem de hashtags) | Sem NLP novo | Menos fiel ao relatório da VHL | Rejeitada pelo autor; BERTopic |
| Circularidade só documentada | Menos código | Uma iteração futura poderia reintroduzir um preditor circular | Rejeitada; checagem em código |
| Análise pontual fora do pipeline, só coeficientes, dashboard depois | Escopo mínimo (recomendação inicial) | — | Rejeitada pelo autor; estágio persistido, previsão/resíduo por post |
| Manter o notebook antigo como histórico | — | Risco de alguém rodar ou citar a análise circular | Rejeitada; removido |

## Validação

Resultados das saídas salvas dos notebooks, que **parecem ser de dado sintético** (ver "Dados e série"):

| | Vídeo (`06`) | Estático (`07`) |
|---|---|---|
| Entrada | 300 reels, 15 governadores | 300 posts, 15 governadores |
| Governadores em holdout | 7 de 15 | 7 de 15 |
| `alpha` (LassoCV) | 0,0030 | 0,0034 |
| n treino / n holdout | 160 / 140 | 160 / 140 |
| R² de treino | 0,0000 | 0,0000 |
| R² de holdout | -0,9751 | -0,6443 |
| Todos os coeficientes exibidos | 0 | 0 (no trecho salvo) |
| Circularidade | OK | OK |
| Shapiro-Wilk (resíduos de holdout) | W = 0,8782, p = 0,0000 (arredondado; não normal) | W = 0,8959, p = 0,0000 (arredondado; não normal) |
| Durbin-Watson | 0,5973 (possível autocorrelação) | 0,7636 (possível autocorrelação) |
| Breusch-Pagan | p = 0,2159 (sem heterocedasticidade) | p = 0,7698 (sem heterocedasticidade) |
| VIF > 10 | nenhum | `tem_duracao` e `type_raw_Video` (VIF da ordem de 1e15, colineares entre si) |

Leitura: com esses dados o Lasso zera todos os coeficientes (prevê a média) e o R² de holdout é negativo, ou seja, pior que
prever a média do holdout. Isso é compatível com ruído sem sinal, e não diz nada sobre os dados reais dos governadores. O VIF
extremo no grupo estático mostra que `tem_duracao` e `type_raw_Video` são redundantes no conjunto salvo.

- Resultado em dado real: **não registrado**. A ADR 0034 trata `post_performance_*` como tabelas que podem ser puladas "com
  pouco dado" e aparecem só como aviso no relatório de tabelas.
- Testes automatizados do código: `tests/test_post_performance.py`.

## Limitações

- O grupo estático fica permanentemente sem preditor de alcance e sem `paidPartnership`; qualquer leitura dos coeficientes
  precisa comunicar isso (ADR 0019, Consequências).
- Compartilhamentos e salvamentos não estão na coleta, então não entram em `Y` nem nos preditores (ADR 0018).
- Amostra pequena de governadores (a ADR 0019 pensou em ~20/7 ou validação cruzada por governador para 27 perfis); o holdout é
  de 7 governadores.
- O `Wc` muda a cada execução, então o valor de `Y` não é comparável entre execuções (ADR 0018, Consequências).
- `hashtags` e `type` brutos passam a ser colunas Silver de verdade (ADR 0019).
- Os pressupostos do modelo linear não se sustentaram nas saídas salvas (normalidade e autocorrelação), ressalva a rever quando
  houver resultado em dado real.
- O consumo no dashboard previsto na ADR 0019 (Decisão 10, card de "lacuna de execução" em Performance) não existe no
  dashboard atual: nenhum módulo em `dashboard/` referencia as tabelas `post_performance_*` (busca feita ao escrever esta ficha),
  e a ADR 0021 reorganizou o dashboard por decisão. Só o `DeltaRepository` expõe os métodos `load_post_performance_*`.

## Vínculos

- Código: [`src/modeling/post_performance.py`](../../src/modeling/post_performance.py), [`src/modeling/topics.py`](../../src/modeling/topics.py) (`classify_post_topics`), [`src/modeling/config.py`](../../src/modeling/config.py) (`PostPerformanceConfig`), [`src/modeling/orchestration.py`](../../src/modeling/orchestration.py)
- ADR: [0019](../adr/0019-regressao-de-performance-por-post-video-e-estatico-com-lasso-e-bertopic.md), [0018](../adr/0018-realinhar-engajamento-e-matriz-de-quadrantes-ao-relatorio-vhl-sem-produto-deputados.md), [0021](../adr/0021-dashboard-organizado-por-decisao-com-funil-como-tela-dedicada.md), [0034](../adr/0034-pipeline-ponto-unico-ugc-no-extrator-comentarios-de-posts-janela-e-relatorio.md)
- Notebooks: [`06_regressao_performance_video.ipynb`](../../notebooks/06_regressao_performance_video.ipynb), [`07_regressao_performance_estatico.ipynb`](../../notebooks/07_regressao_performance_estatico.ipynb)
- TCC (capítulo/seção): a preencher
