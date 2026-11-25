"""Regra do Código de campanha sobre o rótulo de sentimento (ADR 0048).

Fora do pipeline desde a ADR 0049: o classificador ajustado ao domínio venceu a
regra em teste reservado
(`notebooks/modelagens/sentimento_02_comparacao_de_metodos.ipynb`). O módulo
fica como o método comparado, usado pelos notebooks de validação.

O classificador pré-treinado (`cardiffnlp/twitter-xlm-roberta-base-sentiment`)
foi treinado em tuítes e lê como `neutral` o apoio escrito no código das
campanhas no Instagram: número de candidato e emojis de apoio ("5️⃣5️⃣💙🚀",
"4️⃣0️⃣0️⃣✅", "🚀🚀🚀"). A regra é um pós-processamento determinístico: só
reclassifica `neutral` em `positive`, nunca mexe em `positive`/`negative`, e
guarda o rótulo original do modelo em `sentiment_label_modelo`.
"""

from __future__ import annotations

import re

import pandas as pd

EMOJIS_DE_APOIO = frozenset("❤♥💙💚💜🤍💛🧡🚀✅👏🙌🙏😍🥰👍💯⭐✌🤝💪🎉😘")
EMOJIS_DE_REPROVACAO = frozenset("🤮👎😡🤬🤡💩😠😤🤢😢😭😔😞💔")
# Com letras, a regra só vale para textos curtos: um número de candidato e um
# emoji de apoio dentro de um texto longo não bastam para decidir o sentimento.
MAX_PALAVRAS = 6

_PALAVRA = re.compile(r"[^\W\d_]+")
_DIGITO = re.compile(r"\d")

COLUNA_ROTULO_MODELO = "sentiment_label_modelo"


def is_codigo_de_campanha(texto: object) -> bool:
    """True se o texto é apoio em Código de campanha: tem emoji de apoio, não
    tem emoji de reprovação e, ou não tem letras (só números e emojis), ou tem
    número e no máximo `MAX_PALAVRAS` palavras."""
    if not isinstance(texto, str):
        return False
    if not any(ch in EMOJIS_DE_APOIO for ch in texto):
        return False
    if any(ch in EMOJIS_DE_REPROVACAO for ch in texto):
        return False
    palavras = _PALAVRA.findall(texto)
    if not palavras:
        return True
    return bool(_DIGITO.search(texto)) and len(palavras) <= MAX_PALAVRAS


def apply_codigo_de_campanha(df: pd.DataFrame, text_column: str = "text") -> pd.DataFrame:
    """Guarda o rótulo do classificador em `sentiment_label_modelo` e
    reclassifica como `positive` os comentários `neutral` em Código de
    campanha. Idempotente: reaplicar parte sempre do rótulo original do modelo.
    `sentiment_score` não muda (segue sendo a confiança do classificador no
    rótulo que ele deu)."""
    df = df.copy()
    if COLUNA_ROTULO_MODELO not in df.columns:
        df[COLUNA_ROTULO_MODELO] = df["sentiment_label"]
    original = df[COLUNA_ROTULO_MODELO]
    promovido = (original == "neutral") & df[text_column].map(is_codigo_de_campanha)
    df["sentiment_label"] = original.where(~promovido, "positive")
    return df
