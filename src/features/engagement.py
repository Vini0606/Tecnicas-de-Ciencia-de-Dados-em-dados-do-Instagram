import pandas as pd


class EngagementFeatureBuilder:
    """
    Responsabilidade única: calcular métricas de engajamento (RFM-like).
    Recebe DataFrames limpos, devolve DataFrame enriquecido.
    """

    def build(
        self,
        df_profiles: pd.DataFrame,
        df_posts: pd.DataFrame,
        df_reels: pd.DataFrame,
    ) -> pd.DataFrame:
        df_posts = df_posts.copy()
        df_reels = df_reels.copy()

        df_posts["data_hora"] = (
            pd.to_datetime(df_posts["timestamp"])
            .dt.tz_convert("America/Sao_Paulo")
            .dt.tz_localize(None)
        )
        df_reels["data_hora"] = (
            pd.to_datetime(df_reels["timestamp"])
            .dt.tz_convert("America/Sao_Paulo")
            .dt.tz_localize(None)
        )
        df_reels["Total de Engajamento"] = (
            df_reels["commentsCount"] + df_reels["likesCount"]
        )

        df_posts["Tipo"] = "FEED"
        df_reels["Tipo"] = "REELS"
        df_combined = pd.concat([df_posts, df_reels], axis=0)

        grouped = (
            df_combined.groupby(["ownerId", "ownerUsername"])
            .agg(
                commentsSum=("commentsCount", "sum"),
                likesSum=("likesCount", "sum"),
                minData=("data_hora", "min"),
                maxData=("data_hora", "max"),
                count=("ownerId", "count"),
            )
            .reset_index()
        )

        df = pd.merge(
            df_profiles,
            grouped,
            left_on="id",
            right_on="ownerId",
            how="left",
        ).drop(columns=["ownerId"])

        df["TOTAL ENGAJAMENTO"] = df["commentsSum"] + df["likesSum"]
        df["% ENGAJAMENTO"] = df["TOTAL ENGAJAMENTO"] / df["followersCount"]
        df["RECENCIA"] = 1 / ((df["maxData"].max() - df["maxData"]).dt.days + 1)
        df["FREQUENCIA"] = df["count"] / ((df["maxData"] - df["minData"]).dt.days + 1)

        return df, df_combined
