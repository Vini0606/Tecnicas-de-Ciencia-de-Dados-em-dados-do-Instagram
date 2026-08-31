"""
Consolida os `run_id` espalhados por `data/landing/`, `data/logs/`,
`data/model_checkpoints/`, `data/backfill/` e as colunas `_run_id` da
Bronze/Silver/Gold numa visao unica -- sem isso, entender "o que gerou
esse run_id e o que existe dele" exige cruzar timestamps manualmente
entre pastas que nunca tiveram a intencao de bater 1:1 (extracao e
modelagem sempre tem run_id proprios, ver ADR 0001; nem todo script
loga, ver ADR 0015).

`data/calibration/` fica de fora de proposito: os relatorios de
`run_apify_calibration_test.py` nao tem `run_id` nenhum, so um
timestamp solto (`stamp`) -- nao ha o que correlacionar.

Uso:
    uv run python scripts/inspect_runs.py                # lista todos os run_id conhecidos
    uv run python scripts/inspect_runs.py --run-id <ID>   # detalhe de um run_id especifico
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deltalake import DeltaTable

from config import settings

BRONZE_TABLES = {
    "profiles": settings.BRONZE_PROFILES,
    "posts": settings.BRONZE_POSTS,
    "reels": settings.BRONZE_REELS,
}
SILVER_TABLES = {
    "profiles_clean": settings.SILVER_PROFILES,
    "posts_clean": settings.SILVER_POSTS,
    "reels_clean": settings.SILVER_REELS,
    "comments_clean": settings.SILVER_COMMENTS,
    "governors_metadata": settings.SILVER_GOVERNORS_METADATA,
}
GOLD_TABLES = {
    "governor_engagement": settings.GOLD_ENGAGEMENT,
    "governor_sentiment": settings.GOLD_SENTIMENT,
    "governor_clusters": settings.GOLD_CLUSTERS,
    "governor_profile_clusters_engagement": settings.GOLD_PROFILE_CLUSTERS_ENGAGEMENT,
}
# governor_engagement e escrito por toda invocacao de run_medallion_pipeline,
# com ou sem --run-modeling -- nao e sinal de modelagem, ao contrario dos
# outros tres (saida de run_deterministic_modeling/lambdas/model).
GOLD_MODELING_TABLES = {
    "governor_sentiment",
    "governor_clusters",
    "governor_profile_clusters_engagement",
}


def _delta_run_id_counts(path) -> dict[str, int]:
    """run_id -> contagem de linhas. {} se a tabela nao existe ou nao tem
    a coluna _run_id (schemas Delta antigos/dado vazio)."""
    try:
        df = DeltaTable(str(path)).to_pandas()
    except Exception:
        return {}
    if "_run_id" not in df.columns or df.empty:
        return {}
    return df["_run_id"].value_counts().to_dict()


def _dir_run_ids(base: Path) -> set[str]:
    if not base.exists():
        return set()
    return {p.name for p in base.iterdir() if p.is_dir()}


def _backfill_report_run_ids() -> dict[str, Path]:
    """run_id -> caminho do relatorio. O nome do arquivo so tem a janela e
    um timestamp; o run_id de verdade so existe dentro do JSON."""
    backfill_dir = settings.DATA_DIR / "backfill"
    result: dict[str, Path] = {}
    if not backfill_dir.exists():
        return result
    for report_path in backfill_dir.glob("backfill_report_*.json"):
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        run_id = data.get("run_id")
        if run_id:
            result[run_id] = report_path
    return result


def _parse_timestamp_from_run_id(run_id: str) -> str:
    """run_id no formato de src/run_id.py::build_run_id (YYYYMMDD_HHMMSS_hex8)
    tem o timestamp embutido; outros formatos (uuid4 do scraper legado, ids
    sinteticos de teste, etc.) nao -- devolve "?" nesse caso."""
    parts = run_id.split("_")
    if len(parts) >= 2 and len(parts[0]) == 8 and len(parts[1]) == 6:
        try:
            return datetime.strptime(f"{parts[0]}_{parts[1]}", "%Y%m%d_%H%M%S").strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except ValueError:
            pass
    return "?"


def collect() -> dict[str, dict]:
    landing_ids = _dir_run_ids(settings.LANDING_DIR)
    logs_ids = _dir_run_ids(settings.LOGS_DIR)
    checkpoint_ids = _dir_run_ids(settings.MODEL_CHECKPOINTS_DIR)
    backfill_reports = _backfill_report_run_ids()

    bronze_counts = {name: _delta_run_id_counts(path) for name, path in BRONZE_TABLES.items()}
    silver_counts = {name: _delta_run_id_counts(path) for name, path in SILVER_TABLES.items()}
    gold_counts = {name: _delta_run_id_counts(path) for name, path in GOLD_TABLES.items()}

    all_run_ids: set[str] = landing_ids | logs_ids | checkpoint_ids | set(backfill_reports)
    for counts in (*bronze_counts.values(), *silver_counts.values(), *gold_counts.values()):
        all_run_ids |= set(counts.keys())

    records: dict[str, dict] = {}
    for run_id in all_run_ids:
        bronze = {k: v[run_id] for k, v in bronze_counts.items() if run_id in v}
        silver = {k: v[run_id] for k, v in silver_counts.items() if run_id in v}
        gold = {k: v[run_id] for k, v in gold_counts.items() if run_id in v}

        # Extracao e modelagem nunca compartilham run_id (ADR 0001) -- se
        # os dois sinais aparecerem juntos aqui, e sinal de colisao real
        # (ou de dado sintetico de teste reaproveitando um id à toa).
        # bronze so recebe linha nova numa extracao real (extract_and_land) --
        # silver/governor_engagement sao recalculados em toda invocacao de
        # run_medallion_pipeline, inclusive no caminho de cache-hit (sem
        # extracao nova nenhuma), entao sozinhos nao provam extracao.
        is_extraction = run_id in landing_ids or run_id in backfill_reports or bool(bronze)
        is_modeling = run_id in checkpoint_ids or bool(GOLD_MODELING_TABLES & gold.keys())
        is_etl_recalculado = bool(silver) or "governor_engagement" in gold

        # Curto de proposito -- ver LEGENDA_TIPOS, impressa junto da tabela
        # (uma string longa aqui estoura a largura da coluna e desalinha
        # tudo depois dela). Sem acento tambem de proposito -- console do
        # Windows (cp1252) engasga com caracteres acentuados em print() nao
        # protegido.
        if is_extraction and is_modeling:
            tipo = "extracao+modelagem(!)"
        elif is_extraction:
            tipo = "extracao"
        elif is_modeling:
            tipo = "modelagem"
        elif is_etl_recalculado:
            tipo = "etl-cache-hit"
        else:
            tipo = "desconhecido"

        records[run_id] = {
            "tipo": tipo,
            "quando": _parse_timestamp_from_run_id(run_id),
            "landing": run_id in landing_ids,
            "logs": run_id in logs_ids,
            "checkpoint": run_id in checkpoint_ids,
            "backfill_report": backfill_reports.get(run_id),
            "bronze": bronze,
            "silver": silver,
            "gold": gold,
        }
    return records


LEGENDA_TIPOS = {
    "etl-cache-hit": "Silver/governor_engagement recalculados via cache-hit, sem extracao nova",
    "extracao+modelagem(!)": "mesmo run_id com sinal de extracao E de modelagem -- nao deveria acontecer (ADR 0001), investigar",
}

_COLUNAS = ["run_id", "tipo", "quando", "landing", "logs", "ckpt", "bronze", "silver", "gold"]


def _linha(r: dict) -> list[str]:
    return [
        r["tipo"],
        r["quando"],
        "sim" if r["landing"] else "-",
        "sim" if r["logs"] else "-",
        "sim" if r["checkpoint"] else "-",
        str(sum(r["bronze"].values()) or "-"),
        str(sum(r["silver"].values()) or "-"),
        str(sum(r["gold"].values()) or "-"),
    ]


def print_list(records: dict[str, dict]) -> None:
    if not records:
        print("Nenhum run_id encontrado em data/.")
        return

    ordenados = sorted(records.items(), key=lambda kv: kv[1]["quando"])
    linhas = [[run_id, *_linha(r)] for run_id, r in ordenados]

    # Largura por coluna calculada a partir do conteudo real (nao um chute
    # fixo) -- um valor mais longo que o esperado (ex: "extracao+modelagem(!)")
    # so alarga a coluna dele, nunca desalinha as outras.
    larguras = [
        max(len(_COLUNAS[i]), max((len(linha[i]) for linha in linhas), default=0))
        for i in range(len(_COLUNAS))
    ]

    def _formata(valores: list[str]) -> str:
        return "  ".join(v.ljust(w) for v, w in zip(valores, larguras))

    cabecalho = _formata(_COLUNAS)
    print(cabecalho)
    print("-" * len(cabecalho))
    for linha in linhas:
        print(_formata(linha))

    tipos_presentes = {r["tipo"] for r in records.values()}
    legenda_relevante = {t: LEGENDA_TIPOS[t] for t in tipos_presentes if t in LEGENDA_TIPOS}
    if legenda_relevante:
        print()
        for tipo, explicacao in legenda_relevante.items():
            print(f"{tipo} = {explicacao}")


def print_detail(run_id: str, records: dict[str, dict]) -> None:
    # Sem acento de proposito -- console do Windows (cp1252) engasga com
    # caracteres acentuados em print() nao protegido.
    r = records.get(run_id)
    if r is None:
        print(f"run_id '{run_id}' nao encontrado em nenhuma fonte conhecida (landing/logs/checkpoint/backfill/Bronze/Silver/Gold).")
        return

    print(f"run_id: {run_id}")
    print(f"  tipo: {r['tipo']}")
    print(f"  quando (se codificado no run_id): {r['quando']}")
    print(f"  landing zone: {settings.LANDING_DIR / run_id if r['landing'] else 'nao'}")
    print(f"  log: {settings.LOGS_DIR / run_id / 'pipeline.log' if r['logs'] else 'nao'}")
    print(f"  checkpoint de modelagem: {settings.MODEL_CHECKPOINTS_DIR / run_id if r['checkpoint'] else 'nao'}")
    print(f"  relatorio de backfill: {r['backfill_report'] or 'nao'}")
    print(f"  Bronze: {r['bronze'] or 'nenhuma linha'}")
    print(f"  Silver: {r['silver'] or 'nenhuma linha'}")
    print(f"  Gold: {r['gold'] or 'nenhuma linha'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Inspeciona os run_id espalhados por data/ (landing, logs, checkpoints, backfill, Bronze/Silver/Gold)."
    )
    parser.add_argument(
        "--run-id", default=None, help="Mostra o detalhe de um run_id específico em vez da lista completa."
    )
    args = parser.parse_args()

    all_records = collect()
    if args.run_id:
        print_detail(args.run_id, all_records)
    else:
        print_list(all_records)
