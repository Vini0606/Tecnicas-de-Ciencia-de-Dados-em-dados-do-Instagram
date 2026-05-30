from abc import ABC, abstractmethod

import pandas as pd


class DataRepository(ABC):
    """
    Interface abstrata para repositório de dados processados.
    Os dashboards dependem desta abstração, não de uma implementação concreta.
    """

    @abstractmethod
    def load_profiles(self) -> pd.DataFrame: ...

    @abstractmethod
    def load_posts(self) -> pd.DataFrame: ...

    @abstractmethod
    def load_reels(self) -> pd.DataFrame: ...

    @abstractmethod
    def load_comments(self) -> pd.DataFrame: ...

    @abstractmethod
    def save(self, dataframes: dict[str, pd.DataFrame]) -> None: ...
