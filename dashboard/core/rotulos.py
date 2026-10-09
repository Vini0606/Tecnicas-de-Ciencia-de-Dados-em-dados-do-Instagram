"""Rótulos de tópico legíveis e sem identificar terceiros (ADR 0038).

Os nomes de tópico vêm do BERTopic ("25_defendam_incontestáveis_reconheço_227"):
um prefixo de id, palavras-chave coladas por `_`, e, nos comentários, quase
sempre a descrição de emojis em português ("mãos aplaudindo", "tecla 3",
"coração vermelho"). Este módulo, sem Streamlit nem I/O:

- remove o prefixo de id e troca `_` por vírgula (`rotular_topico`);
- reconhece tópicos que são só emojis e dá um nome legível (`rotulo_se_emoji`);
- extrai as menções `@usuario` de terceiros dos textos e as tira dos nomes
  (`extrair_mencoes`, `remover_mencoes`), para um rótulo nunca expor o @ de um
  cidadão comum. Perfis dos próprios governadores são figuras públicas e ficam.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

import pandas as pd

MAX_CHARS_ROTULO = 60
# Mínimo de caracteres para uma menção virar token removível: evita tirar
# palavras comuns que também existem como @ (ex.: "@brasil").
MIN_CHARS_MENCAO = 8

_PREFIXO_ID_RE = re.compile(r"^-?\d+_")
_MENCAO_RE = re.compile(rf"@([\w.]{{{MIN_CHARS_MENCAO},30}})")

# Palavras de ligação que aparecem nas descrições de emoji ("rosto chorando de rir").
_LIGACAO = frozenset(
    {"de", "da", "do", "e", "a", "o", "as", "os", "aos", "com", "para", "em"}
)

# Família -> palavras que a identificam. Todas contam como "palavra de emoji".
_FAMILIAS_EMOJI: dict[str, frozenset[str]] = {
    "Emojis de mãos e aplausos": frozenset(
        {
            "mãos",
            "aplaudindo",
            "juntas",
            "pele",
            "clara",
            "escura",
            "média",
            "polegar",
            "positivo",
        }
    ),
    "Emojis de corações": frozenset(
        {
            "coração",
            "vermelho",
            "verde",
            "azul",
            "laranja",
            "amarelo",
            "roxo",
            "rosa",
            "preto",
            "branco",
        }
    ),
    "Emojis de rostos": frozenset(
        {
            "rosto",
            "sorridente",
            "risonho",
            "sorridentes",
            "olhos",
            "chorando",
            "rir",
            "berros",
            "segurando",
            "lágrimas",
            "piscando",
            "beijo",
        }
    ),
    "Emojis de números": frozenset({"tecla", "marca", "seleção", "branca"}),
    "Emojis de bandeiras e símbolos": frozenset(
        {
            "bandeira",
            "brasil",
            "foguete",
            "balão",
            "fogos",
            "festa",
            "estrela",
            "brilho",
            "chama",
            "fogo",
        }
    ),
}
# Palavras de direção das descrições de emoji ("seta para cima e para a direita"):
# contam como palavra de emoji, mas não votam no nome da família.
_NEUTRAS_EMOJI = frozenset({"seta", "cima", "baixo", "direita", "esquerda"})
_ROTULO_EMOJI_GENERICO = "Reação só com emojis"
_LIMIAR_EMOJI = 0.75


def _tokens(name: object) -> list[str]:
    """Palavras-chave do nome, sem o prefixo de id. `[]` para nulo."""
    if name is None or (not isinstance(name, str) and pd.isna(name)):
        return []
    texto = _PREFIXO_ID_RE.sub("", str(name).strip(), count=1)
    return [t for t in re.split(r"[_,\s]+", texto) if t]


def _eh_palavra_de_emoji(token: str) -> bool:
    t = token.lower()
    return (
        t.isdigit()
        or t in _NEUTRAS_EMOJI
        or any(t in palavras for palavras in _FAMILIAS_EMOJI.values())
    )


def rotulo_se_emoji(name: object) -> str | None:
    """Nome legível se o tópico for (quase) só descrição de emojis; senão `None`.
    "Quase": pelo menos 75% das palavras que não são de ligação são palavras de
    emoji ou números ("bandeira brasil brasil coração verde" conta; "foguete
    balão hélder estourou" não)."""
    significativos = [t for t in _tokens(name) if t.lower() not in _LIGACAO]
    if not significativos:
        return None
    de_emoji = [t for t in significativos if _eh_palavra_de_emoji(t)]
    if len(de_emoji) / len(significativos) < _LIMIAR_EMOJI:
        return None
    pontos = {
        familia: sum(1 for t in de_emoji if t.lower() in palavras)
        for familia, palavras in _FAMILIAS_EMOJI.items()
    }
    familia, melhor = max(pontos.items(), key=lambda kv: kv[1])
    return familia if melhor > 0 else _ROTULO_EMOJI_GENERICO


def rotular_topico(name: object, max_chars: int = MAX_CHARS_ROTULO) -> str:
    """Rótulo de exibição de um tópico de comentário: o nome legível dos
    tópicos de emoji; senão as palavras-chave separadas por vírgula, sem o
    prefixo de id e truncadas. Nunca lança exceção; nulo vira texto neutro."""
    emoji = rotulo_se_emoji(name)
    if emoji:
        return emoji
    tokens = _tokens(name)
    if not tokens:
        return "Tema sem rótulo definido"
    texto = ", ".join(tokens)
    if len(texto) > max_chars:
        texto = texto[: max_chars - 1].rstrip(", ") + "…"
    return texto


def extrair_mencoes(textos: Iterable[object]) -> frozenset[str]:
    """Menções `@usuario` (minúsculas, com `MIN_CHARS_MENCAO`+ caracteres) dos textos."""
    achadas: set[str] = set()
    for texto in textos:
        if isinstance(texto, str):
            achadas.update(m.lower().rstrip(".") for m in _MENCAO_RE.findall(texto))
    return frozenset(a for a in achadas if len(a) >= MIN_CHARS_MENCAO)


def remover_mencoes(name: object, mencoes: frozenset[str]) -> object:
    """Tira do nome as palavras que são menções de terceiros, mantendo o formato
    (`12_a_b_c` ou `a, b, c`) e o prefixo de id. Nunca devolve um nome vazio."""
    if not mencoes or not isinstance(name, str):
        return name
    separador = ", " if ", " in name else "_"
    partes = name.split(separador)
    mantidas = [
        p
        for i, p in enumerate(partes)
        if (i == 0 and separador == "_" and p.lstrip("-").isdigit())
        or p.strip().lower() not in mencoes
    ]
    return separador.join(mantidas) if mantidas else name
