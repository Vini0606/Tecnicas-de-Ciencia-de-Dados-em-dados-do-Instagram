---
status: superseded by ADR-0049
---

# Regra do Código de campanha sobre o rótulo de sentimento

> Substituída pela ADR [0049](0049-classificador-de-sentimento-dos-comentarios-ajustado-ao-dominio.md): o ajuste fino do
> classificador, que esta ADR deixava como trabalho futuro, foi feito e venceu a regra em teste reservado. A regra saiu do
> pipeline e `scripts/apply_sentiment_rule.py` deu lugar a `scripts/reclassify_comment_sentiment.py`. O texto abaixo fica como
> registro da decisão anterior.

## Contexto

O sentimento dos comentários vem do `cardiffnlp/twitter-xlm-roberta-base-sentiment`, usado sem ajuste. A aprovação que entra na
NSM, na dimensão Qualidade do Escore composto e no Score ICE é a proporção de comentários `positive`. Até a revisão do TCC para a
banca, nenhum rótulo tinha sido conferido.

A validação em amostra anotada (`notebooks/modelagens/sentimento_01_validacao_amostra_anotada.ipynb`, 300 comentários estratificados
pela classe prevista mais 60 de Reels virais) mostrou:

- precisão de 94% em `positive`, 76% em `negative` e **23% em `neutral`**; acurácia estimada na população de 70,6%;
- de cada 100 comentários `neutral`, 73 eram apoio, quase sempre em **Código de campanha** (ver `CONTEXT.md`): número de candidato
  com emoji de apoio ("5️⃣5️⃣💙🚀", "4️⃣0️⃣0️⃣✅"), ou só emojis de apoio;
- a proporção de positivos era de 61,2% pelo classificador e de 80,9% pela anotação; a de negativos, 7,8% nos dois;
- o viés era desigual entre perfis (de 1 a 36 pontos percentuais de aprovação), porque depende de quanto do apoio de cada público
  vem nesse código. O ranking de aprovação por perfil, e com ele a dimensão Qualidade, não era confiável.

## Decisão

Aplicar, depois do classificador e só nos comentários, um pós-processamento determinístico (`src/modeling/sentiment_rules.py`):

> Um comentário `neutral` passa a `positive` quando o texto tem ao menos um emoji de apoio, não tem emoji de reprovação e, ou não
> tem letras (só números e emojis), ou tem número e no máximo seis palavras.

- A regra só promove `neutral` a `positive`. Nunca altera `positive` nem `negative`.
- `governor_sentiment` e `governor_sentiment_history` ganham a coluna `sentiment_label_modelo`, com o rótulo original do
  classificador. `sentiment_label` passa a ser o rótulo já corrigido, e é o que todos os consumidores continuam lendo.
- `sentiment_score` não muda: segue sendo a confiança do classificador no rótulo que ele deu.
- A regra roda dentro de `run_deterministic_modeling` e pode ser reaplicada sobre uma Gold existente com
  `scripts/apply_sentiment_rule.py`, que recalcula só as tabelas dependentes (Score ICE de temas e de pautas, NSM, Escore composto,
  métricas de crescimento) sem reexecutar o classificador nem o BERTopic.
- Número de candidato sem emoji de apoio ("22", "13 13") continua `neutral`: sem saber de quem é o perfil, pode ser apoio ou
  provocação.

Uma segunda amostra, de 100 comentários atingidos pela regra e fora da primeira, mediu a precisão da regra em 99% (IC 95% de 94,6%
a 99,8%). Com a regra, a acurácia estimada sobe para 85,2% e a proporção de positivos para 75,7%.

## Alternativas consideradas

- **Só reportar o viés no TCC, sem corrigir.** Mantinha todos os números publicados, mas deixava o ranking de aprovação e a
  dimensão Qualidade sem validade por perfil, o que enfraquecia o Escore composto e os estudos de caso.
- **Trocar ou ajustar o classificador** (modelo treinado em português político, ou *fine-tuning* com anotação própria). É a correção
  de fundo, mas exige um conjunto anotado bem maior do que 460 comentários e reexecução completa. Fica como trabalho futuro.
- **Tratar número de candidato isolado como apoio.** Ampliaria a cobertura, mas a polaridade não é decidível pelo texto, e a
  acurácia cairia segundo o critério de anotação.

## Consequências

- A aprovação por perfil muda de +0,8 a +35,7 pontos percentuais; 20 dos 24 perfis com amostra suficiente mudam de posição em
  aprovação. Na NSM, 9 de 24 mudam de posição (correlação de postos de 0,99 com a versão anterior). No Escore composto, 19 dos 26
  perfis mudam de posição.
- Os números de sentimento, NSM, Score ICE e Escore composto do TCC e do dashboard mudam e precisam ser atualizados; uma nova Coleta
  modelada precisa ser publicada no Hugging Face (com aval explícito, ver `docs/agents/coletas.md`).
- Resta um viés de cerca de cinco pontos na aprovação: apoio em texto que o classificador lê como neutro e que não tem a forma do
  Código de campanha. A classe `neutral` continua a menos confiável (precisão de 43,4%).
- A lista de emojis e o limite de seis palavras foram calibrados em uma Coleta de período eleitoral. Fora dele o Código de campanha
  pode ter outra forma; a regra deve ser revalidada em cada nova Coleta usada para conclusões.
- A anotação que sustenta a decisão foi feita por modelo de linguagem, às cegas, e conferida pelo autor; não há segundo anotador
  humano independente.
- Um checkpoint gravado antes desta ADR não tem `sentiment_label_modelo`. Se `scripts/refine_topics.py` for rodado sobre ele, a
  Gold de sentimento volta ao rótulo do classificador e `scripts/apply_sentiment_rule.py` precisa ser rodado em seguida.
