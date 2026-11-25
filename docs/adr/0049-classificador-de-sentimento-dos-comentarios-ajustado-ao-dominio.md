---
status: accepted
---

# Classificador de sentimento dos comentários ajustado ao domínio

## Contexto

A validação em amostra anotada mostrou que o `cardiffnlp/twitter-xlm-roberta-base-sentiment`, usado sem ajuste, subestimava a
aprovação nos comentários (61,2% de positivos contra cerca de 80% pela anotação), com erro desigual entre perfis. A ADR
[0048](0048-regra-do-codigo-de-campanha-sobre-o-rotulo-de-sentimento.md) corrigiu a parte desse erro que tinha forma fixa, o
**Código de campanha**, com uma regra determinística, e deixou o ajuste fino do classificador como trabalho futuro.

O ajuste fino foi então feito e comparado com as duas alternativas em um experimento com conjunto de teste reservado
(`notebooks/modelagens/sentimento_02_comparacao_de_metodos.ipynb`):

- **Teste:** 450 comentários novos, 150 por classe prevista pelo classificador original, anotados às cegas antes do treino; as
  métricas são pós-estratificadas para a população.
- **Treino:** 1.482 comentários anotados com o mesmo critério escrito (`validacao_sentimento/criterio_anotacao.md`).
- **Desenvolvimento:** a amostra da primeira validação (360 comentários), usada para escolher taxa de aprendizado e época.
- **Vazamento:** nenhum texto (chave normalizada) e nenhuma publicação do teste aparecem no treino; o script de treino não lê os
  rótulos do teste; o critério de escolha foi fixado antes de ver o teste.

| Método | F1-macro (IC 95%) | Acurácia | Positivos previstos | Negativos previstos |
| :--- | :--- | :--- | :--- | :--- |
| Classificador original | 65,7% (61,2 a 70,1) | 74,7% | 61,2% | 7,8% |
| Original + regra do Código de campanha | 74,5% (69,6 a 79,4) | 86,9% | 73,4% | 7,8% |
| Ajuste fino | 85,1% (80,2 a 89,6) | 93,9% | 80,6% | 10,3% |

A anotação estima 80,2% de positivos e 8,9% de negativos. A diferença de F1-macro entre o ajuste fino e a regra é de +10,6 pontos
(IC 95% de +4,6 a +16,8). O F1 da classe `negative` não piora (69,7% para 79,0%; diferença com IC de −0,3 a +18,9).

## Decisão

O sentimento dos **comentários** passa a vir do classificador ajustado, sem a regra do Código de campanha por cima.

- O modelo é o XLM-RoBERTa da cardiffnlp com o treino continuado nos 1.482 comentários anotados (taxa 3e-5, 2 épocas, lote 16,
  corte de 64 tokens, perda ponderada por classe, semente fixa). Fica em `data/model_checkpoints/sentimento_ajuste_fino/` e é
  gerado por `notebooks/modelagens/validacao_sentimento/ajuste_fino.py`.
- `ModelingConfig.comment_sentiment` aponta para esse modelo, com o mesmo corte de 64 tokens do treino e da avaliação.
  `ModelingConfig.sentiment` (pré-treinado) segue valendo para **legenda e transcrição**, que não fizeram parte do treino nem do
  teste.
- `sentiment_label` e `sentiment_score` dos comentários são o rótulo e a confiança do modelo ajustado. `sentiment_label_modelo`
  guarda o rótulo do classificador pré-treinado quando ele existe (a Coleta do TCC), para auditoria; em execuções novas do
  pipeline fica nulo.
- `scripts/reclassify_comment_sentiment.py` reclassifica uma Gold existente e recalcula só as tabelas dependentes (Score ICE de
  temas e de pautas, NSM, Escore composto, métricas de crescimento), sem reexecutar o BERTopic.
- A regra (`src/modeling/sentiment_rules.py`) sai do pipeline e fica como método comparado, usada só pelos notebooks de
  validação.

## Alternativas consideradas

- **Manter a regra do Código de campanha (ADR 0048).** Tem precisão de 99% no que alcança e não depende de anotação, mas não
  alcança apoio em texto corrido ("Bora Lula", "Tem meu voto") nem crítica lida como neutra. Ficou 10,6 pontos de F1-macro abaixo.
- **Ajuste fino com a regra por cima.** Não foi avaliado antes de abrir o teste; escolher essa combinação depois de ver o
  resultado seria ajustar a decisão ao teste.
- **Ajustar também as legendas.** Não há legenda anotada; aplicar o modelo a um gênero em que não foi treinado nem testado seria
  trocar um erro medido por um erro desconhecido.

## Consequências

- Os números de sentimento, NSM, Score ICE e Escore composto do TCC e do dashboard mudam de novo e precisam ser atualizados; uma
  nova Coleta modelada precisa ser publicada no Hugging Face (com aval explícito, ver `docs/agents/coletas.md`).
- O pipeline passa a depender de um artefato local que não está no git nem no Snapshot. Sem a pasta do modelo, a modelagem falha
  com mensagem que aponta para o script de treino. Publicar o modelo é decisão pendente.
- **Anotador em comum.** Treino e teste foram anotados pelo mesmo modelo de linguagem, com o mesmo critério. Não é vazamento de
  dados, mas parte da vantagem do ajuste fino pode ser concordância com esse anotador. A conferência do autor na planilha do
  teste é o que mede isso.
- Uma única semente e duas taxas de aprendizado: a variação entre execuções de treino não foi medida.
- O modelo foi ajustado em uma Coleta de período eleitoral. Em outro período, deve ser revalidado antes de sustentar conclusões.
- Um checkpoint de modelagem gravado antes desta ADR traz o rótulo do classificador pré-treinado. Se `scripts/refine_topics.py`
  for rodado sobre ele, a Gold de sentimento volta a esse rótulo e `scripts/reclassify_comment_sentiment.py` precisa ser rodado em
  seguida.
