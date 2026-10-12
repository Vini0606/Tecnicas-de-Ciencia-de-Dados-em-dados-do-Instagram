# Sentimento dos comentários (e de legendas e transcrições)

**Status:** a documentar
**Atualizada em:** 2026-10-11

> Justificativa do status: o modelo está em uso e alimenta NSM, Escore composto, Score ICE e os cartões de aprovação, mas
> nenhuma fonte registra validação do classificador contra rótulos humanos nem comparação com outro modelo. A própria
> configuração (`SentimentConfig`) e a ADR 0020 declaram que a qualidade em texto formal não foi validada.

## Pergunta de negócio

O público reage de forma positiva ou negativa ao que o governador publica? A resposta alimenta:

- o **Engajamento qualificado** (comentários positivos sobre comentários totais; ver [nsm.md](nsm.md));
- a dimensão **Qualidade** do Escore composto (ver [escore-composto-cmgr.md](escore-composto-cmgr.md));
- a seleção de **Grupos de comentários** positivos e negativos por governador e o Score ICE de priorização;
- o estágio Convert do Funil (comentários positivos) e os cartões de "Melhor aprovação" e "Maior rejeição"
  (ADR 0032, ADR 0038).

## Dados e série

- Tabela Gold: `governor_sentiment`, com `sentiment_label` e `sentiment_score` por linha, e a tabela paralela
  `governor_sentiment_history` (modo append).
- Três fontes na mesma tabela, discriminadas pela coluna `fonte`: `comentario`, `legenda` (caption de post) e `transcricao`
  (fala do reel, via `includeTranscript` do actor de reels) (ADR 0020, Ficha 3; `src/modeling/orchestration.py`).
- Comentários vêm de duas origens, `reel` e `post`, na coluna `origem_comentario` (nula em legenda e transcrição); um comentário
  capturado nas duas conta uma vez, como `reel` (ADR 0034, `CONTEXT.md`).
- O texto de entrada é o texto original (`text`), sem remoção de stopwords nem conversão de emojis; esse pré-processamento
  só é aplicado ao pipeline de tópicos (`src/modeling/orchestration.py`, ordem das chamadas).
- Escala do diagnóstico salvo (`notebooks/diagnostico_medallion/gold_sentiment.ipynb`, execução anterior à coluna
  `origem_comentario`): 4.268 linhas; 3.574 `id_comment` distintos; 332 linhas sem `sentiment_label` (7,78%); 3 valores
  distintos de `sentiment_label`; 2 execuções acumuladas no histórico. O notebook reporta ainda 693 linhas duplicadas por
  `id_comment` e 694 `id_comment` nulos, sem investigá-los.
- Mediana de comentários por governador: 302 (ADR 0038, dado de 2026-10-08); o piso prático dos cartões de aprovação é 30
  comentários (`MIN_COMENTARIOS_CARTAO`, ADR 0038), um valor prático e não um teste estatístico.
- Os números mudam com a Coleta: a ADR 0034 passou a incluir comentários de posts, e a Coleta final (90 dias, #256) ainda
  não foi feita.

## Método escolhido

`analyze_sentiment` (`src/modeling/sentiment.py`) aplica o pipeline `sentiment-analysis` do Hugging Face com o modelo
`cardiffnlp/twitter-xlm-roberta-base-sentiment` (`SentimentConfig.model_name`), com truncamento em 512 tokens. Texto nulo ou
vazio, ou falha de inferência, resulta em rótulo e score nulos (sem erro). O código de negócio trata como positivo o rótulo
`positive` (NSM, Escore composto). A mesma configuração é reaproveitada para as três fontes; só a coluna de texto muda.

## Alternativas avaliadas

Nenhuma alternativa está registrada nas fontes consultadas (ADRs, código, notebooks): não há comparação com outros modelos
(por exemplo, outro classificador em português ou léxico), com outros limiares, nem com anotação manual. Não registrado.

## Validação

- **Sem validação de acurácia registrada.** Nenhuma fonte traz precisão, F1 ou concordância com rotulagem humana.
- **Limitação declarada de domínio:** o modelo foi treinado em tweets (texto curto e informal). Legenda e transcrição de
  assessoria são texto mais longo e formal, um registro diferente do domínio de treino; a qualidade do rótulo nesse texto "não
  foi validada com dado real" e deve ser declarada como limitação no Cap. 7 do TCC (docstring de `SentimentConfig`; ADR 0020,
  Ficha 3, e o mesmo aviso para o texto de terceiros do UGC, Ficha 8).
- **Diagnóstico de tabela:** `gold_sentiment.ipynb` mostra, na execução salva, média de 61,77% de comentários positivos entre
  perfis com desvio de 47,10 e nenhum perfil a mais de 2 desvios-padrão; o notebook alerta que `% positivo` por perfil é
  sensível ao volume de comentários. Esse valor não é um indicador de qualidade do classificador.
- **Consequência visível em auditoria:** "Melhor aprovação 100%" vinha de um perfil com 3 comentários (ADR 0038), o que levou
  ao piso de 30 comentários.
- Testes automatizados do código: `tests/test_sentiment.py` (com pipeline simulado).

## Limitações

- Modelo treinado em tweets, aplicado a comentários de Instagram e a texto formal de assessoria (ADR 0020).
- Muitos comentários são só emoji (ADR 0038 descreve os tópicos de comentário como "quase todos emojis"); o comportamento do
  classificador sobre comentário só com emoji não está registrado.
- A proporção positiva de um perfil é instável com poucos comentários (nota de interpretação do notebook; ADR 0038).
- Só uma amostra dos comentários mais recentes de cada publicação é coletada (`docs/research/apify-instagram-actors-cobra-mapping.md`,
  `latestComments`).
- Truncamento em 512 tokens para qualquer texto.
- O histórico entre execuções (`governor_sentiment_history`) perde função no desenho da ADR 0039: a comparação temporal passa a
  vir de dentro de uma Coleta, e só o dashboard ainda lê `load_sentiment_history`.

## Vínculos

- Código: [`src/modeling/sentiment.py`](../../src/modeling/sentiment.py), [`src/modeling/config.py`](../../src/modeling/config.py) (`SentimentConfig`), [`src/modeling/orchestration.py`](../../src/modeling/orchestration.py), [`src/modeling/comment_sources.py`](../../src/modeling/comment_sources.py)
- ADR: [0020](../adr/0020-alinhamento-tcc-funil-cobra-race-nsm-ice-cmgr-e-reformulacao-do-dashboard-de-growth.md) (Fichas 3 e 8), [0034](../adr/0034-pipeline-ponto-unico-ugc-no-extrator-comentarios-de-posts-janela-e-relatorio.md), [0038](../adr/0038-correcoes-da-auditoria-rotulos-amostra-minima-e-privacidade.md), [0039](../adr/0039-coleta-versionada-no-hf-bronze-fiel-e-aws-so-reconstroi.md), [0003](../adr/0003-desacoplar-modelagem-do-notebook-via-scripts-cli-com-checkpoint.md)
- Notebooks: [`gold_sentiment.ipynb`](../../notebooks/diagnostico_medallion/gold_sentiment.ipynb), [`03_modelagem_hibrida.ipynb`](../../notebooks/03_modelagem_hibrida.ipynb) (distribuição de rótulos, sem saída salva)
- TCC (capítulo/seção): a preencher
