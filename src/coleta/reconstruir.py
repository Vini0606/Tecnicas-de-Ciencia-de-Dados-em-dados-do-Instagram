"""
Reconstrucao das camadas a partir de um Snapshot do HF (ADR 0039, issue #253).

Baixa o Snapshot de uma tag e reconstroi Bronze, Silver e Gold em `destino`
(pasta local ou `s3://bucket/prefixo`) usando so etapas deterministicas:

- Bronze: copia fiel das tabelas do Snapshot (a verdade vem do HF);
- Silver: governadores copiados (vem da planilha, nao da Bronze); o resto e
  derivado da Bronze por `derivar_silver_gold`;
- Gold: engajamento e UGC derivados; as demais tabelas Gold do Snapshot
  (saidas da modelagem pesada, ja calculadas na Coleta) sao copiadas como
  estao -- nada de BERTopic nem de Apify aqui.

O cliente do HF e injetado; o unico segredo (token) vive no cliente real.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from deltalake import DeltaTable, write_deltalake

from src.coleta.derivacao import caminhos_do_destino, derivar_silver_gold
from src.coleta.hf import ClienteColetaHF, baixar
from src.data_extract.bronze_writer import BronzeWriter
from src.run_id import build_run_id

logger = logging.getLogger(__name__)

_TABELAS_BRONZE = ("instagram_profiles", "instagram_posts", "instagram_reels", "ugc_mentions")
# Gold regerado pela derivacao: nao e copiado do Snapshot.
_GOLD_DERIVADO = {"governor_engagement", "governor_engagement_history", "governor_ugc_mentions"}


class ErroReconstrucao(RuntimeError):
    """O Snapshot nao tem o minimo para reconstruir as camadas."""


def _juntar(base: Path | str, *partes: str) -> str:
    if "://" in str(base):
        return "/".join([str(base).rstrip("/"), *partes])
    return str(Path(base).joinpath(*partes))


def _copiar_tabela(origem: Path, destino: str) -> int:
    """Copia uma tabela Delta preservando o schema; devolve o numero de linhas."""
    tabela = DeltaTable(str(origem)).to_pyarrow_table()
    write_deltalake(destino, tabela, mode="overwrite")
    return tabela.num_rows


def _username_da_url(url: str) -> str:
    return urlparse(url).path.strip("/").split("/")[0]


def reconstruir(
    tag: str,
    destino: Path | str,
    *,
    cliente: ClienteColetaHF,
    run_id: str | None = None,
    pasta_trabalho: Path | str | None = None,
) -> dict:
    """Reconstroi Bronze, Silver e Gold de `tag` em `destino`. Devolve um
    resumo (tag, run_id, tabelas copiadas e derivadas). `pasta_trabalho` e o
    disco temporario do download (no Lambda, `/tmp`); removido ao final."""
    run_id = build_run_id(run_id)
    raiz = Path(tempfile.mkdtemp(prefix="reconstruir_", dir=pasta_trabalho))
    try:
        snapshot = baixar(tag, raiz / "snapshot", cliente=cliente)
        return _reconstruir_de(snapshot, tag, destino, run_id)
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


def _reconstruir_de(snapshot: Path, tag: str, destino: Path | str, run_id: str) -> dict:
    metadados = snapshot / "silver" / "governors_metadata"
    if not (metadados / "_delta_log").is_dir():
        raise ErroReconstrucao(
            f"Snapshot {tag} sem silver/governors_metadata: não há como saber quais governadores filtrar"
        )
    for nome in ("instagram_profiles", "instagram_posts", "instagram_reels"):
        if not (snapshot / "bronze" / nome / "_delta_log").is_dir():
            raise ErroReconstrucao(f"Snapshot {tag} sem bronze/{nome}")

    copiadas: list[str] = []
    for nome in _TABELAS_BRONZE:
        origem = snapshot / "bronze" / nome
        if (origem / "_delta_log").is_dir():
            _copiar_tabela(origem, _juntar(destino, "bronze", nome))
            copiadas.append(f"bronze/{nome}")

    _copiar_tabela(metadados, _juntar(destino, "silver", "governors_metadata"))
    copiadas.append("silver/governors_metadata")
    urls = DeltaTable(str(metadados)).to_pandas()["inputUrl"]
    usernames = sorted({_username_da_url(u) for u in urls if u})

    origem_p = caminhos_do_destino(snapshot)
    bronze = BronzeWriter(
        bronze_profiles_path=origem_p["bronze_profiles"],
        bronze_posts_path=origem_p["bronze_posts"],
        bronze_reels_path=origem_p["bronze_reels"],
        bronze_ugc_mentions_path=origem_p["bronze_ugc"],
    )
    derivar_silver_gold(
        bronze, caminhos_do_destino(destino), usernames, run_id, modo_historico="overwrite"
    )

    gold = snapshot / "gold"
    if gold.is_dir():
        for tabela in sorted(gold.iterdir()):
            if tabela.name in _GOLD_DERIVADO or not (tabela / "_delta_log").is_dir():
                continue
            _copiar_tabela(tabela, _juntar(destino, "gold", tabela.name))
            copiadas.append(f"gold/{tabela.name}")

    logger.info("[RECONSTRUIR] %s: %d tabela(s) copiada(s), Silver/Gold derivados.", tag, len(copiadas))
    return {"tag": tag, "run_id": run_id, "governadores": len(usernames), "copiadas": copiadas}
