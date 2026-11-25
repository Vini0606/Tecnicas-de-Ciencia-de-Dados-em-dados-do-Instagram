"""Amostragem da validação do classificador de sentimentos (Seção 5.4 do TCC).

Sorteia, da Gold `governor_sentiment`, os comentários que serão anotados e
grava dois arquivos separados, para que a anotação seja feita às cegas:

- `amostra_para_rotular.csv`: só `id_amostra` e `text`, em ordem embaralhada;
- `gabarito_modelo.csv`: `id_amostra`, estrato, rótulo e escore do modelo e as
  chaves do comentário. Só é lido depois de a anotação estar fechada.

Uso (a partir da raiz do repositório):

    python notebooks/modelagens/validacao_sentimento/amostragem.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SEED = 20261119
N_POR_CLASSE = 100
N_VIRAL_POR_CLASSE = 20
CLASSES = ["positive", "neutral", "negative"]
CLUSTER_VIRAL = 2  # grupo dos 27 Reels virais (Seção 5.3.1 do TCC)

PASTA = Path(__file__).resolve().parent
ARQ_AMOSTRA = PASTA / "amostra_para_rotular.csv"
ARQ_GABARITO = PASTA / "gabarito_modelo.csv"


def carregar_populacao(repo) -> pd.DataFrame:
    """Comentários classificados (exclui legendas e os comentários sem rótulo),
    com a marca `viral` para os comentários dos Reels do grupo viral."""
    from src.modeling.sentiment_rules import is_codigo_de_campanha

    df = repo.load_comments()
    # Depois da ADR 0049 a Gold guarda em `sentiment_label` o rótulo do
    # classificador ajustado e em `sentiment_label_modelo` o do pré-treinado.
    # A validação avalia o pré-treinado, então `sentiment_label` volta a ser o
    # rótulo dele aqui. O rótulo com a regra do Código de campanha (ADR 0048) é
    # recalculado, e o do modelo ajustado fica em `sentiment_label_ajuste`.
    df["sentiment_label_ajuste"] = df["sentiment_label"]
    if "sentiment_label_modelo" in df.columns:
        df["sentiment_label"] = df["sentiment_label_modelo"].fillna(df["sentiment_label"])
    promovido = (df["sentiment_label"] == "neutral") & df["text"].map(is_codigo_de_campanha)
    df["sentiment_label_regra"] = df["sentiment_label"].where(~promovido, "positive")
    df = df[(df["fonte"] == "comentario") & df["sentiment_label"].notna()].copy()
    reels = repo.load_clusters_reels()
    virais = set(reels.loc[reels["cluster_label"] == CLUSTER_VIRAL, "id_reel"])
    df["viral"] = df["id_reel"].isin(virais)
    return df.sort_values("id_comment").reset_index(drop=True)


def sortear(populacao: pd.DataFrame) -> pd.DataFrame:
    """Dois estratos de sorteio, ambos estratificados pela classe prevista:

    - `principal`: `N_POR_CLASSE` comentários por classe, sorteados de toda a
      população (é a amostra que sustenta as métricas gerais);
    - `viral`: até `N_VIRAL_POR_CLASSE` por classe, sorteados só entre os
      comentários de Reels virais ainda não sorteados (suplemento para olhar o
      classificador exatamente onde está o achado central do trabalho).
    """
    partes = []
    for i, classe in enumerate(CLASSES):
        grupo = populacao[populacao["sentiment_label"] == classe]
        partes.append(
            grupo.sample(n=N_POR_CLASSE, random_state=SEED + i).assign(estrato="principal")
        )
    principal = pd.concat(partes)

    restantes = populacao[populacao["viral"] & ~populacao["id_comment"].isin(principal["id_comment"])]
    partes = []
    for i, classe in enumerate(CLASSES):
        grupo = restantes[restantes["sentiment_label"] == classe]
        n = min(N_VIRAL_POR_CLASSE, len(grupo))
        partes.append(grupo.sample(n=n, random_state=SEED + 10 + i).assign(estrato="viral"))
    suplemento = pd.concat(partes)

    amostra = pd.concat([principal, suplemento])
    amostra = amostra.sample(frac=1, random_state=SEED).reset_index(drop=True)
    amostra.insert(0, "id_amostra", [f"A{i:03d}" for i in range(1, len(amostra) + 1)])
    return amostra


COLUNAS_GABARITO = [
    "id_amostra",
    "estrato",
    "viral",
    "sentiment_label",
    "sentiment_score",
    "id_comment",
    "id_reel",
    "origem_comentario",
]


def main() -> None:
    from src.repositories.delta_repository import DeltaRepository

    raiz = PASTA.parents[2]
    repo = DeltaRepository(raiz / "data" / "gold", raiz / "data" / "silver", raiz / "data" / "bronze")
    amostra = sortear(carregar_populacao(repo))
    amostra[["id_amostra", "text"]].to_csv(ARQ_AMOSTRA, index=False, encoding="utf-8")
    amostra[COLUNAS_GABARITO].to_csv(ARQ_GABARITO, index=False, encoding="utf-8")
    print(f"{len(amostra)} comentários sorteados")
    print(amostra.groupby("estrato").size().to_string())


if __name__ == "__main__":
    main()
