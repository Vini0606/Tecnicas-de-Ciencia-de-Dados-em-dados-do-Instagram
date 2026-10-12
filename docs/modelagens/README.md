# Catálogo de modelagens

Uma ficha por modelagem do projeto. A ficha é a visão viva ("o que é, como foi avaliado, em que pé está"); o ADR registra a
decisão; o notebook é a prova; o TCC conta a história.

## Status

| Status | Significado |
|---|---|
| `em avaliação` | Há uma pergunta aberta e notebooks comparando métodos. Não está em produção. |
| `validada` | Método escolhido com evidência registrada e em uso. |
| `descartada` | Avaliada e abandonada; a ficha guarda o motivo. |
| `a documentar` | Existe no código, mas a ficha ainda não foi preenchida. |

## Inventário

| Modelagem | Ficha | Status |
|---|---|---|
| Tendência própria (substitui o Comparativo vs. mediana) | [tendencia.md](tendencia.md) | em avaliação |
| Clusterização de perfis e de comentários | [clusterizacao.md](clusterizacao.md) | a documentar |
| Tópicos de discurso e de comentário (BERTopic) | [topicos.md](topicos.md) | a documentar |
| Sentimento dos comentários | [sentimento.md](sentimento.md) | a documentar |
| Engajamento qualificado (NSM) | [nsm.md](nsm.md) | validada |
| Regressão de performance por post (Lasso) | [regressao-performance-post.md](regressao-performance-post.md) | a documentar |
| Escore composto e CMGR de engajamento | [escore-composto-cmgr.md](escore-composto-cmgr.md) | a documentar |

## Como usar

- Nova modelagem ou nova alternativa para uma existente: copie [TEMPLATE.md](TEMPLATE.md), preencha, adicione ao inventário.
- Notebooks de avaliação vivem em `notebooks/modelagens/`, um por modelagem em avaliação, com o esqueleto do template.
- Toda mudança de status atualiza a ficha **e** esta tabela.
- Ao decidir de forma difícil de reverter, escreva um ADR e linke-o na ficha.
