# Sentimento dos comentários (e de legendas e transcrições)

**Status:** validada em amostra anotada por modelo de linguagem (comentários); legendas e transcrições a documentar
**Atualizada em:** 2026-11-20

> Justificativa do status: o classificador dos comentários foi validado em amostra anotada, comparado com duas alternativas em
> teste reservado e substituído pelo modelo ajustado ao domínio (ADR 0049). A anotação é de modelo de linguagem, às cegas e sob
> critério escrito, com conferência do autor pendente; não há segundo anotador humano. Legenda e transcrição seguem no modelo
> pré-treinado, sem validação.

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

`analyze_sentiment` (`src/modeling/sentiment.py`) aplica o pipeline `sentiment-analysis` do Hugging Face. Texto nulo ou vazio, ou
falha de inferência, resulta em rótulo e score nulos (sem erro). O código de negócio trata como positivo o rótulo `positive`
(NSM, Escore composto).

- **Comentários** (`ModelingConfig.comment_sentiment`): classificador ajustado ao domínio, isto é, o
  `cardiffnlp/twitter-xlm-roberta-base-sentiment` com o treino continuado em 1.482 comentários anotados da Coleta do TCC (taxa
  3e-5, 2 épocas, corte de 64 tokens). Fica em `data/model_checkpoints/sentimento_ajuste_fino/`, gerado por
  `notebooks/modelagens/validacao_sentimento/ajuste_fino.py` (ADR 0049).
- **Legenda e transcrição** (`ModelingConfig.sentiment`): o modelo pré-treinado, com truncamento em 512 tokens.
- Para reclassificar uma Gold já gravada sem refazer o BERTopic: `scripts/reclassify_comment_sentiment.py`.

## Alternativas avaliadas

Comparadas em um conjunto de teste reservado de 450 comentários
([`sentimento_02_comparacao_de_metodos.ipynb`](../../notebooks/modelagens/sentimento_02_comparacao_de_metodos.ipynb)):

| Método | F1-macro (IC 95%) | Acurácia | Positivos previstos |
| :--- | :--- | :--- | :--- |
| Classificador pré-treinado | 65,7% (61,2 a 70,1) | 74,7% | 61,2% |
| Pré-treinado + regra do Código de campanha (ADR 0048) | 74,5% (69,6 a 79,4) | 86,9% | 73,4% |
| Ajuste fino (adotado) | 85,1% (80,2 a 89,6) | 93,9% | 80,6% |

A anotação estima 80,2% de positivos. O critério de escolha foi fixado antes de ver o teste (maior F1-macro com diferença
distinguível de zero; em empate, o mais simples; sem piorar a classe `negative`).

## Validação

- **Primeira validação** ([`sentimento_01_validacao_amostra_anotada.ipynb`](../../notebooks/modelagens/sentimento_01_validacao_amostra_anotada.ipynb)):
  360 comentários anotados. O pré-treinado tinha acurácia de 70,6% e precisão de 94% em `positive`, 76% em `negative` e 23% em
  `neutral`; 73 de cada 100 "neutros" eram apoio em Código de campanha.
- **Teste reservado:** tabela acima. Nenhum texto normalizado nem publicação do teste aparece no treino; o treino não lê os
  rótulos do teste.
- **Anotação:** modelo de linguagem, às cegas (só o texto), segundo
  [`criterio_anotacao.md`](../../notebooks/modelagens/validacao_sentimento/criterio_anotacao.md). Treino e teste têm o mesmo
  anotador, então parte da vantagem do ajuste fino pode ser concordância com ele. As planilhas `*_conferencia.xlsx` existem para
  a conferência do autor, ainda pendente.
- **Legenda e transcrição:** sem validação. O modelo pré-treinado foi treinado em tweets, e a qualidade do rótulo em texto formal
  de assessoria não foi medida (docstring de `SentimentConfig`; ADR 0020, Ficha 3).
- Testes automatizados do código: `tests/test_sentiment.py` (com pipeline simulado) e `tests/test_sentiment_rules.py`.

## Limitações

- O modelo dos comentários foi ajustado em uma Coleta de período eleitoral, com uma única semente; fora desse período deve ser
  revalidado. O pipeline depende de um artefato local (a pasta do modelo), que não está no git nem no Snapshot.
- Legenda e transcrição usam o modelo treinado em tweets, sem validação em texto formal de assessoria (ADR 0020).
- O sentimento é o do texto, não a posição diante do governador: parte dos comentários negativos tem um terceiro como alvo.
- A proporção positiva de um perfil é instável com poucos comentários (nota de interpretação do notebook; ADR 0038).
- Só uma amostra dos comentários mais recentes de cada publicação é coletada (`docs/research/apify-instagram-actors-cobra-mapping.md`,
  `latestComments`).
- Truncamento em 64 tokens nos comentários (como no treino) e em 512 em legenda e transcrição.
- O histórico entre execuções (`governor_sentiment_history`) perde função no desenho da ADR 0039: a comparação temporal passa a
  vir de dentro de uma Coleta, e só o dashboard ainda lê `load_sentiment_history`.

## Vínculos

- Código: [`src/modeling/sentiment.py`](../../src/modeling/sentiment.py), [`src/modeling/config.py`](../../src/modeling/config.py) (`SentimentConfig`), [`src/modeling/orchestration.py`](../../src/modeling/orchestration.py), [`src/modeling/comment_sources.py`](../../src/modeling/comment_sources.py)
- ADR: [0020](../adr/0020-alinhamento-tcc-funil-cobra-race-nsm-ice-cmgr-e-reformulacao-do-dashboard-de-growth.md) (Fichas 3 e 8), [0048](../adr/0048-regra-do-codigo-de-campanha-sobre-o-rotulo-de-sentimento.md), [0049](../adr/0049-classificador-de-sentimento-dos-comentarios-ajustado-ao-dominio.md), [0034](../adr/0034-pipeline-ponto-unico-ugc-no-extrator-comentarios-de-posts-janela-e-relatorio.md), [0038](../adr/0038-correcoes-da-auditoria-rotulos-amostra-minima-e-privacidade.md), [0039](../adr/0039-coleta-versionada-no-hf-bronze-fiel-e-aws-so-reconstroi.md), [0003](../adr/0003-desacoplar-modelagem-do-notebook-via-scripts-cli-com-checkpoint.md)
- Notebooks: [`gold_sentiment.ipynb`](../../notebooks/diagnostico_medallion/gold_sentiment.ipynb), [`03_modelagem_hibrida.ipynb`](../../notebooks/03_modelagem_hibrida.ipynb) (distribuição de rótulos, sem saída salva)
- TCC (capítulo/seção): Capítulo 5, Seção "Análise de Sentimentos", subseção "Validação do Classificador e Ajuste ao Domínio"
