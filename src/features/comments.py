import pandas as pd


class CommentsTransformer:
    """
    Responsabilidade única: explodir e limpar comentários aninhados dos reels.
    """

    MAX_TEXT_LENGTH: int = 512
    COLUMNS_TO_DROP: list[str] = [
        "hashtags",
        "mentions",
        "images",
        "childPosts",
        "musicInfo",
        "replies",
        "taggedUsers",
        "coauthorProducers",
    ]

    def transform(self, df_reels: pd.DataFrame) -> pd.DataFrame:
        # Proteções: se a coluna não existir, retorna DataFrame vazio
        if "latestComments" not in df_reels.columns:
            return pd.DataFrame()

        # Explode comentários (trata valores None/NaN corretamente)
        df_exploded = df_reels.copy()
        df_exploded["latestComments"] = df_exploded["latestComments"].apply(
            lambda v: v if isinstance(v, list) else ([v] if pd.notna(v) else [])
        )
        df_exploded = df_exploded.explode("latestComments").copy()

        # Normaliza cada comentário em colunas separadas
        df_normalized = pd.json_normalize(
            df_exploded["latestComments"].apply(lambda x: x or {})
        )
        df_normalized.index = df_exploded.index

        df = df_exploded.drop("latestComments", axis=1).join(
            df_normalized, lsuffix="_reel", rsuffix="_comment"
        )

        # Se não existir a coluna de texto, cria para evitar KeyError
        if "text" not in df.columns:
            df["text"] = ""

        cols_to_drop = [c for c in self.COLUMNS_TO_DROP if c in df.columns]
        if cols_to_drop:
            df = df.drop(columns=cols_to_drop)

        df["comprimento texto"] = df["text"].astype(str).str.len()
        df = df[df["comprimento texto"] < self.MAX_TEXT_LENGTH]
        df = df.drop_duplicates()

        return df
