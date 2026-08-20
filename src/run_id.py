"""Geração do identificador de execução compartilhado pelo Medallion e pela modelagem."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def build_run_id(run_id: str | None = None) -> str:
    if run_id:
        return run_id
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{uuid.uuid4().hex[:8]}"
