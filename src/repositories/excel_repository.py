from pathlib import Path

import pandas as pd

from src.repositories.base import DataRepository
from src.schemas import PROFILES_DTYPE, REELS_DTYPE


class ExcelDataRepository(DataRepository):
    """LEGACY Excel repository implementation: reads and writes processed data in .xlsx format."""

    def __init__(self, path: Path):
        self._path = path

    def load_profiles(self) -> pd.DataFrame:
        return pd.read_excel(self._path, sheet_name="profiles", dtype=PROFILES_DTYPE)

    def load_posts(self) -> pd.DataFrame:
        return pd.read_excel(self._path, sheet_name="posts", dtype=REELS_DTYPE)

    def load_reels(self) -> pd.DataFrame:
        return pd.read_excel(self._path, sheet_name="reels", dtype=REELS_DTYPE)

    def load_comments(self) -> pd.DataFrame:
        return pd.read_excel(self._path, sheet_name="reels_latestComments")

    def save(self, dataframes: dict[str, pd.DataFrame]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(self._path, engine="openpyxl") as writer:
            for sheet_name, df in dataframes.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
