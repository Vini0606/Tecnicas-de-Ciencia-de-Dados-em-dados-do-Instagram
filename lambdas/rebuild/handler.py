"""Lambda de reconstrucao (ADR 0039, issue #253).

Evento: {"tag": "coleta_...", "run_id": "opcional"}. Baixa o Snapshot da tag no
Hugging Face e reconstroi Bronze, Silver e Gold no S3, so com etapas
deterministicas (sem Apify, sem modelagem pesada).

Ambiente: S3_BUCKET (obrigatorio), S3_BASE_PREFIX (opcional, ex. "dados/"),
HF_TOKEN e HF_DATASET_REPO (lidos so pelo cliente real do HF). `DESTINO_URI`,
se definido, substitui `s3://S3_BUCKET/S3_BASE_PREFIX` (usado em testes).
"""

import json
import logging
import os

from src.coleta.hf import ClienteColetaHFReal, ErroColetaHF
from src.coleta.reconstruir import ErroReconstrucao, reconstruir

logger = logging.getLogger(__name__)

# Delta no S3 sem lock no DynamoDB (mesmo ajuste das demais Lambdas).
os.environ.setdefault("AWS_S3_ALLOW_UNSAFE_RENAME", "true")


def _criar_cliente():
    return ClienteColetaHFReal()


def handler(event, context):
    event = event or {}
    tag = event.get("tag")
    if not tag:
        return {"statusCode": 400, "body": "Missing tag in event"}

    destino = os.environ.get("DESTINO_URI", "")
    if not destino:
        bucket = os.environ.get("S3_BUCKET", "")
        if not bucket:
            return {"statusCode": 400, "body": "Missing S3_BUCKET"}
        destino = f"s3://{bucket}/{os.environ.get('S3_BASE_PREFIX', '')}"

    try:
        resumo = reconstruir(
            tag,
            destino,
            cliente=_criar_cliente(),
            run_id=event.get("run_id"),
            pasta_trabalho=os.environ.get("TMPDIR") or None,
        )
    except (ErroColetaHF, ErroReconstrucao, ValueError) as exc:
        logger.error("[REBUILD] falha ao reconstruir %s: %s", tag, exc)
        return {
            "statusCode": 422,
            "body": json.dumps({"tag": tag, "erro": str(exc)}, ensure_ascii=False),
        }

    return {"statusCode": 200, "body": json.dumps({**resumo, "status": "rebuild_complete"})}
