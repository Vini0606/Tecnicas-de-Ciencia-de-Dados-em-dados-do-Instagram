"""Partição de dados do experimento de comparação de métodos de sentimento
(`sentimento_02_comparacao_de_metodos.ipynb`).

Três conjuntos, sorteados nesta ordem e sem interseção:

- **teste** (450 comentários, 150 por classe prevista pelo classificador
  original): só serve para a comparação final. É sorteado da população inteira,
  exceto os comentários das amostras da primeira validação, porque essas
  amostras serviram para desenhar a regra do Código de campanha.
- **desenvolvimento**: as amostras da primeira validação (360 comentários já
  anotados). Serve para escolher época e taxa de aprendizado do ajuste fino.
- **treino**: sorteado do que sobra depois de retirar (a) todo comentário cujo
  texto normalizado aparece no teste ou no desenvolvimento e (b) todo
  comentário de uma publicação que tem comentário no teste.

A chave de texto normalizado (`chave_texto`) trata como o mesmo texto as
variações de caixa, de espaço e de repetição ("👏👏👏" e "👏👏👏👏"), para que o
modelo ajustado não seja avaliado em textos que, na prática, decorou.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import amostragem as am
import pandas as pd

N_TESTE_POR_CLASSE = 150
N_TREINO_ALEATORIO = 900
N_TREINO_NEGATIVE = 350
N_TREINO_NEUTRAL = 350

PASTA = Path(__file__).resolve().parent
ARQ_TESTE = PASTA / "teste_para_rotular.csv"
ARQ_TESTE_GABARITO = PASTA / "teste_gabarito_modelo.csv"
ARQ_TREINO = PASTA / "treino_para_rotular.csv"

_DESCARTAR = re.compile(r"[\s️‍\U0001F3FB-\U0001F3FF]+")
_REPETICAO = re.compile(r"(.)\1+", flags=re.DOTALL)


def chave_texto(texto: object) -> str:
    """Texto sem diferença de caixa, espaço, tom de pele e repetição de caractere."""
    t = unicodedata.normalize("NFKC", str(texto)).casefold()
    t = _DESCARTAR.sub("", t)
    return _REPETICAO.sub(r"\1", t)


def ids_da_primeira_validacao() -> set[str]:
    ids = set(pd.read_csv(am.ARQ_GABARITO)["id_comment"].astype(str))
    return ids | set(pd.read_csv(PASTA / "amostra_regra.csv")["id_comment"].astype(str))


def sortear_teste(populacao: pd.DataFrame) -> pd.DataFrame:
    disponivel = populacao[~populacao["id_comment"].astype(str).isin(ids_da_primeira_validacao())]
    partes = [
        disponivel[disponivel["sentiment_label"] == classe].sample(
            n=N_TESTE_POR_CLASSE, random_state=am.SEED + 200 + i
        )
        for i, classe in enumerate(am.CLASSES)
    ]
    teste = pd.concat(partes).sample(frac=1, random_state=am.SEED + 200).reset_index(drop=True)
    teste.insert(0, "id_amostra", [f"T{i:03d}" for i in range(1, len(teste) + 1)])
    return teste


def sortear_treino(populacao: pd.DataFrame, teste: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por texto normalizado distinto, já sem nada que encoste no
    teste ou no desenvolvimento."""
    desenvolvimento = pd.read_csv(am.ARQ_AMOSTRA)
    chaves_vetadas = set(teste["text"].map(chave_texto)) | set(desenvolvimento["text"].map(chave_texto))
    publicacoes_vetadas = set(teste["id_reel"].astype(str))

    pool = populacao.assign(chave=populacao["text"].map(chave_texto))
    pool = pool[
        ~pool["chave"].isin(chaves_vetadas)
        & ~pool["id_reel"].astype(str).isin(publicacoes_vetadas)
        & ~pool["id_comment"].astype(str).isin(ids_da_primeira_validacao())
        & (pool["chave"] != "")
    ]
    partes = [
        pool.sample(n=N_TREINO_ALEATORIO, random_state=am.SEED + 300),
        pool[pool["sentiment_label"] == "negative"].sample(n=N_TREINO_NEGATIVE, random_state=am.SEED + 301),
        pool[pool["sentiment_label"] == "neutral"].sample(n=N_TREINO_NEUTRAL, random_state=am.SEED + 302),
    ]
    treino = pd.concat(partes).drop_duplicates("chave").reset_index(drop=True)
    treino.insert(0, "id_amostra", [f"R{i:04d}" for i in range(1, len(treino) + 1)])
    return treino


def main() -> None:
    from src.repositories.delta_repository import DeltaRepository

    raiz = PASTA.parents[2]
    repo = DeltaRepository(raiz / "data" / "gold", raiz / "data" / "silver", raiz / "data" / "bronze")
    populacao = am.carregar_populacao(repo)

    teste = sortear_teste(populacao)
    teste[["id_amostra", "text"]].to_csv(ARQ_TESTE, index=False, encoding="utf-8")
    teste[["id_amostra", "sentiment_label", "sentiment_score", "id_comment", "id_reel", "inputUrl"]].to_csv(
        ARQ_TESTE_GABARITO, index=False, encoding="utf-8"
    )
    treino = sortear_treino(populacao, teste)
    treino[["id_amostra", "text", "id_comment", "id_reel"]].to_csv(ARQ_TREINO, index=False, encoding="utf-8")
    print(f"teste: {len(teste)} comentários; treino: {len(treino)} textos distintos")


if __name__ == "__main__":
    main()
