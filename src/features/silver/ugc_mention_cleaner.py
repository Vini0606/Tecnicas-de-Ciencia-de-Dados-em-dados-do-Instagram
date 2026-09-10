"""
Silver cleaner de UGC de criação (ADR 0020, Ficha 8 / issue #93).

Posts de TERCEIROS que marcam/mencionam o perfil do governador -- ao
contrário de `PostCleaner`/`ProfileCleaner`, aqui o `ownerUsername`/
`authorUsername` bruto é o AUTOR terceiro (o eleitor/seguidor que criou o
UGC), não o governador. A correlação com qual governador o post menciona
vem do campo `mentions` (lista de usernames marcados, serializada como JSON
string pelo `BronzeWriter`), cruzado contra a lista de usernames de
governador informada a `clean()`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import pandas as pd

from src.delta_io import deduplicate_latest, write_delta
from src.schemas_delta import SILVER_UGC_MENTIONS_SCHEMA


class UGCMentionCleaner:
    BOOL_COLUMNS: ClassVar[list[str]] = [
        "authorIsVerified",
        "isPaidPartnership",
        "isAd",
        "isAffiliate",
    ]
    INT64_COLUMNS: ClassVar[list[str]] = ["likesCount", "commentsCount"]

    def clean(
        self,
        df_bronze: pd.DataFrame,
        run_id: str,
        governor_usernames: list[str] | None = None,
    ) -> pd.DataFrame:
        df = df_bronze.copy()

        df = self._drop_unidentifiable_rows(df)
        df = self._deduplicate_by_id_or_short_code(df)
        df = self._normalize_author_username(df)
        df = self._resolve_governor_username(df, governor_usernames or [])
        df = self._parse_timestamp(df)
        df = self._cast_bools(df)
        df = self._cast_int64(df)
        df = self._cast_video_play_count(df)

        df["_source_layer"] = "bronze"
        return df

    def write(self, df_silver: pd.DataFrame, path: Path | str) -> None:
        write_delta(path, df_silver, SILVER_UGC_MENTIONS_SCHEMA)

    def _drop_unidentifiable_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        # `id` e `shortCode` são ambos `nullable=True` no contrato Silver
        # (piloto do actor ainda não confirmou presença garantida de `id`) --
        # mas um registro sem NENHUM dos dois não é dedupável nem rastreável,
        # então é descartado aqui em vez de propagado como lixo.
        has_id = df["id"].notna() if "id" in df.columns else pd.Series(False, index=df.index)
        has_short_code = (
            df["shortCode"].notna()
            if "shortCode" in df.columns
            else pd.Series(False, index=df.index)
        )
        return df[has_id | has_short_code]

    def _deduplicate_by_id_or_short_code(self, df: pd.DataFrame) -> pd.DataFrame:
        # Dedup por `id`/`shortCode` (issue #93): usa `id` quando presente,
        # cai para `shortCode` quando `id` faltar -- uma chave coalescida em
        # vez de duas passagens de `deduplicate_latest`, que dedup por coluna
        # única e deixaria duplicatas cruzadas (id nulo em uma execução,
        # preenchido em outra) passarem.
        if df.empty:
            return df
        id_col = df["id"] if "id" in df.columns else pd.Series(pd.NA, index=df.index)
        short_code_col = (
            df["shortCode"] if "shortCode" in df.columns else pd.Series(pd.NA, index=df.index)
        )
        df = df.assign(_dedup_key=id_col.fillna(short_code_col))
        df = deduplicate_latest(df, id_col="_dedup_key")
        return df.drop(columns=["_dedup_key"])

    def _normalize_author_username(self, df: pd.DataFrame) -> pd.DataFrame:
        # Normaliza os dois nomes de campo candidatos (issue #93: nome exato
        # não confirmado pelo piloto) num único `authorUsername` -- prefere
        # o campo já nomeado `authorUsername`, cai para `ownerUsername`
        # (convenção usada pelos demais actors já integrados ao pipeline).
        author = (
            df["authorUsername"] if "authorUsername" in df.columns else pd.Series(pd.NA, index=df.index)
        )
        owner = (
            df["ownerUsername"] if "ownerUsername" in df.columns else pd.Series(pd.NA, index=df.index)
        )
        df["authorUsername"] = author.fillna(owner)
        if "ownerUsername" in df.columns:
            df = df.drop(columns=["ownerUsername"])
        return df

    def _resolve_governor_username(
        self, df: pd.DataFrame, governor_usernames: list[str]
    ) -> pd.DataFrame:
        # `mentions` chega como JSON string (BronzeWriter serializa qualquer
        # list/dict) -- ex.: '["governador_x", "outro_perfil"]'. Resolve o
        # governador marcado cruzando contra `governor_usernames`; nulo se o
        # campo faltar, vier vazio/inválido, ou não bater com nenhum
        # username conhecido (post não correlacionável a um governador do
        # projeto -- ver limitação declarada na ADR 0020, Ficha 8).
        known = set(governor_usernames)

        def _resolve(raw_mentions) -> str | None:
            if not known or raw_mentions is None or (isinstance(raw_mentions, float) and pd.isna(raw_mentions)):
                return None
            try:
                mentioned = json.loads(raw_mentions) if isinstance(raw_mentions, str) else raw_mentions
            except (json.JSONDecodeError, TypeError):
                return None
            if not isinstance(mentioned, list):
                return None
            for username in mentioned:
                if username in known:
                    return username
            return None

        if "mentions" in df.columns:
            df["governor_username"] = df["mentions"].map(_resolve)
        else:
            df["governor_username"] = pd.NA
        return df.drop(columns=["mentions"], errors="ignore")

    def _parse_timestamp(self, df: pd.DataFrame) -> pd.DataFrame:
        # Mesmo cuidado de `PostCleaner._parse_timestamp`: format="ISO8601"
        # evita que um único timestamp em formato diferente derrube o parse
        # da série inteira via inferência pelo primeiro valor.
        if "timestamp" in df.columns:
            df["data_hora"] = (
                pd.to_datetime(df["timestamp"], errors="coerce", utc=True, format="ISO8601")
                .dt.tz_convert("America/Sao_Paulo")
                .dt.tz_localize(None)
            )
        else:
            df["data_hora"] = pd.NaT
        return df.drop(columns=["timestamp"], errors="ignore")

    def _cast_bools(self, df: pd.DataFrame) -> pd.DataFrame:
        # Ausência de flag de publi (`isPaidPartnership`/`isAd`/`isAffiliate`)
        # é tratada como False (orgânico) -- mesmo padrão de
        # `ProfileCleaner.BOOL_COLUMNS`. Isso é uma decisão de default, não
        # uma confirmação do piloto: se o actor de fato nunca preencher esses
        # campos, todo UGC seria classificado como orgânico por omissão --
        # risco a revisar quando o piloto rodar de verdade.
        for col in self.BOOL_COLUMNS:
            if col in df.columns:
                df[col] = df[col].fillna(False).astype(bool)
            else:
                df[col] = False
        return df

    def _cast_int64(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in self.INT64_COLUMNS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")
            else:
                df[col] = 0
        return df

    def _cast_video_play_count(self, df: pd.DataFrame) -> pd.DataFrame:
        # Nullable (nem todo UGC é vídeo) -- fillna(0) quebraria a distinção
        # entre "não é vídeo" e "vídeo com 0 plays".
        if "videoPlayCount" in df.columns:
            df["videoPlayCount"] = pd.to_numeric(df["videoPlayCount"], errors="coerce").astype("Int64")
        return df
