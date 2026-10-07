"""Rótulos de tópico sem dependência de NLP.

Fica fora de `gemini_refiner.py` (que importa bertopic, scipy e o SDK do Gemini)
para que o dashboard possa usar a constante sem arrastar a pilha de NLP: o
deploy do dashboard instala só o que ele realmente importa (ADR 0036).
"""

# Rótulo explícito do tópico degenerado (sem palavra alguma, ex.: o "1____"
# do discurso real) -- decisão da issue #186: nome honesto em vez de um
# assunto inventado pelo Gemini.
DEGENERATE_TOPIC_LABEL = "sem assunto definido"
