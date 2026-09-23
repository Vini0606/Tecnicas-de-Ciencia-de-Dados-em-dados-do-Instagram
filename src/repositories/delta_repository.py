"""
DeltaRepository implementation
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from deltalake import DeltaTable

from src.repositories.base import DataRepository


def _join(base: str, name: str) -> str:
    """Junta `base` e `name` sem corromper URIs (`pathlib.Path` colapsa as
    barras duplas de um esquema como `s3://`)."""
    if "://" in base:
        return f"{base.rstrip('/')}/{name}"
    return str(Path(base) / name)


class DeltaRepository(DataRepository):
    def __init__(
        self,
        gold_dir: Path | str,
        silver_dir: Path | str | None = None,
        as_of_version: int | None = None,
        as_of_timestamp: str | None = None,
        storage_options: dict | None = None,
    ):
        self._gold_dir = str(gold_dir)
        self._silver_dir = str(silver_dir) if silver_dir is not None else None
        self._as_of_version = as_of_version
        self._as_of_timestamp = as_of_timestamp
        self._storage_options = storage_options or {}

    def load_profiles(self) -> pd.DataFrame:
        return self._load(_join(self._gold_dir, "governor_engagement"))

    def load_engagement_history(self) -> pd.DataFrame:
        """Histórico de engajamento (mode append, uma linha por perfil por
        execução) -- ver ADR 0016. Separada de `load_profiles` porque tem
        granularidade diferente (várias linhas por governador ao longo do
        tempo, não uma só)."""
        return self._load(_join(self._gold_dir, "governor_engagement_history"))

    def load_posts(self) -> pd.DataFrame:
        if self._silver_dir is None:
            raise ValueError("silver_dir não foi configurado neste repositório.")
        return self._load(_join(self._silver_dir, "posts_clean"))

    def load_reels(self) -> pd.DataFrame:
        if self._silver_dir is None:
            raise ValueError("silver_dir não foi configurado neste repositório.")
        return self._load(_join(self._silver_dir, "reels_clean"))

    def load_comments(self) -> pd.DataFrame:
        try:
            return self._load(_join(self._gold_dir, "governor_sentiment"))
        except FileNotFoundError:
            if self._silver_dir is None:
                raise
            return self._load(_join(self._silver_dir, "comments_clean"))

    def load_sentiment_history(self) -> pd.DataFrame:
        """Histórico de sentimento (mode append, uma linha por comentário por
        execução de modelagem) -- ver issue #52 / ADR 0017. Separada de
        `load_comments` porque tem granularidade temporal diferente (várias
        execuções acumuladas, não só a última)."""
        return self._load(_join(self._gold_dir, "governor_sentiment_history"))

    def load_clusters_reels(self) -> pd.DataFrame:
        """`governor_clusters_reels` -- clusterização de conteúdo, granularidade
        de Reel. Tabela separada de `load_clusters_posts()` desde a issue #152:
        `posts_clean`/`reels_clean` (Silver) se sobrepõem (um Reel também é
        capturado pelo post-scraper genérico no grid do perfil), então uma
        tabela única discriminada por `content_type` duplicava o mesmo post
        real sob os dois pipelines de clusterização."""
        return self._load(_join(self._gold_dir, "governor_clusters_reels"))

    def load_clusters_posts(self) -> pd.DataFrame:
        """`governor_clusters_posts` -- clusterização de conteúdo, granularidade
        de post de feed. Ver `load_clusters_reels()`."""
        return self._load(_join(self._gold_dir, "governor_clusters_posts"))

    def load_profile_clusters_engagement(self) -> pd.DataFrame:
        return self._load(_join(self._gold_dir, "governor_profile_clusters_engagement"))

    def load_discourse_topics(self) -> pd.DataFrame:
        """Tópicos do discurso oficial (legenda+transcrição), BERTopic
        separado do de comentários -- ADR 0020 (Ficha 4) / issue #89."""
        return self._load(_join(self._gold_dir, "governor_discourse_topics"))

    def load_topic_priority_score(self) -> pd.DataFrame:
        """Score ICE de priorização de tópicos de comentário -- ADR 0020
        (Ficha 6) / issue #91. Uma linha por tópico, ranking GLOBAL (não por
        governador)."""
        return self._load(_join(self._gold_dir, "topic_priority_score"))

    def load_nsm(self) -> pd.DataFrame:
        """North Star Metric (engajamento qualificado por perfil) -- ADR 0020
        (Ficha 5) / issue #90."""
        return self._load(_join(self._gold_dir, "governor_nsm"))

    def load_nsm_history(self) -> pd.DataFrame:
        """Histórico de NSM (mode append, uma linha por perfil por execução)
        -- ADR 0025 / issue #153, espelha `load_engagement_history()`.

        NOTA: em 2026-09, `NsmScorer.write` grava `governor_nsm` em modo
        `overwrite` por padrão (ver `src/modeling/orchestration.py`, chamada
        sem `mode="append"`) -- nenhum código do pipeline escreve
        `governor_nsm_history` hoje. Este accessor existe para que
        `dashboard/core/data.py::load_nsm_history()` já tenha onde ler assim
        que o lado da pipeline for ajustado (mudança maior, fora do escopo
        da issue #153 -- ver Implementation Decisions/Out of Scope da
        issue); até lá, degrada para `DataFrame` vazio via `FileNotFoundError`
        como qualquer outra tabela Gold ainda não gerada."""
        return self._load(_join(self._gold_dir, "governor_nsm_history"))

    def load_growth_metrics(self) -> pd.DataFrame:
        """CMGR e retenção sobre o histórico acumulado -- ADR 0020 (Ficha 7)
        / issue #92. Resultado declaradamente ilustrativo enquanto pouco
        histórico tiver se acumulado (ver `ilustrativo`/`nota`)."""
        return self._load(_join(self._gold_dir, "governor_growth_metrics"))

    def load_ugc_mentions(self) -> pd.DataFrame:
        """UGC de criação ("Creating" do COBRA) -- ADR 0020 (Ficha 8) / issue
        #93. Uma linha por post de UGC; agregação por governador é uma view
        (`GovernorUGCAggregator.aggregate_by_governor`), não persistida."""
        return self._load(_join(self._gold_dir, "governor_ugc_mentions"))

    def load_post_performance_coefficients(self) -> pd.DataFrame:
        return self._load(_join(self._gold_dir, "post_performance_coefficients"))

    def load_post_performance_predictions(self) -> pd.DataFrame:
        return self._load(_join(self._gold_dir, "post_performance_predictions"))

    def load_governors_metadata(self) -> pd.DataFrame:
        if self._silver_dir is None:
            raise ValueError("silver_dir não foi configurado neste repositório.")
        return self._load(_join(self._silver_dir, "governors_metadata"))

    def save(self, dataframes: dict[str, pd.DataFrame]) -> None:
        raise NotImplementedError(
            "DeltaRepository é somente leitura. Use os writers para escrever."
        )

    def get_table_history(self, table_name: str) -> pd.DataFrame:
        dt = DeltaTable(
            _join(self._gold_dir, table_name), storage_options=self._storage_options
        )
        return pd.DataFrame(dt.history())

    def _load(self, path: str) -> pd.DataFrame:
        try:
            dt = DeltaTable(path, storage_options=self._storage_options)
            if self._as_of_version is not None:
                return dt.load_as_version(self._as_of_version).to_pandas()
            if self._as_of_timestamp is not None:
                return dt.load_with_datetime(self._as_of_timestamp).to_pandas()
            return dt.to_pandas()
        except Exception as e:
            raise FileNotFoundError(
                f"Tabela Delta não encontrada em {path}. Execute o pipeline Medallion primeiro. Detalhe: {e}"
            ) from e
