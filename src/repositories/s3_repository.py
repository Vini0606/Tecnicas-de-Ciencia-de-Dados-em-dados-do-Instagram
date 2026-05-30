import io

import boto3
import pandas as pd

from src.repositories.base import DataRepository


class S3DataRepository(DataRepository):
    """
    Implementação concreta: lê e salva dados no AWS S3.
    """

    def __init__(self, bucket: str, prefix: str = "processed/"):
        self._bucket = bucket
        self._prefix = prefix
        self._s3 = boto3.client("s3")

    def _read_parquet(self, key: str) -> pd.DataFrame:
        obj = self._s3.get_object(Bucket=self._bucket, Key=f"{self._prefix}{key}")
        return pd.read_parquet(io.BytesIO(obj["Body"].read()))

    def load_profiles(self) -> pd.DataFrame:
        return self._read_parquet("profiles.parquet")

    def load_reels(self) -> pd.DataFrame:
        return self._read_parquet("reels.parquet")

    def load_posts(self) -> pd.DataFrame:
        return self._read_parquet("posts.parquet")

    def load_comments(self) -> pd.DataFrame:
        return self._read_parquet("comments.parquet")

    def save(self, dataframes: dict[str, pd.DataFrame]) -> None:
        for name, df in dataframes.items():
            buffer = io.BytesIO()
            df.to_parquet(buffer, index=False)
            buffer.seek(0)
            self._s3.put_object(
                Bucket=self._bucket, Key=f"{self._prefix}{name}.parquet", Body=buffer
            )
