"""Setup de `logging` para `pipeline.py` e `src/modeling/*` (ADR 0015).

Console em INFO (mesmo volume dos `print()`s que substitui); arquivo em DEBUG,
um por `run_id`, em `data/logs/<run_id>/pipeline.log`. O handler de arquivo
troca (não acumula) a cada `run_id` novo -- ver `attach_run_log_handler`.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_FILE_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_CONSOLE_FORMAT = "%(message)s"

_current_run_file_handler: logging.FileHandler | None = None


def configure_console_logging(level: int = logging.INFO) -> None:
    """Configura o logger raiz para aceitar até DEBUG (a filtragem real fica a
    cargo de cada handler) e garante um único `StreamHandler` de console, em
    `level`. Idempotente -- seguro chamar mais de uma vez no mesmo processo."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    for handler in root.handlers:
        if getattr(handler, "_is_console_handler", False):
            return

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
    console_handler._is_console_handler = True  # type: ignore[attr-defined]
    root.addHandler(console_handler)


def attach_run_log_handler(run_id: str, logs_dir: Path) -> None:
    """Troca o handler de arquivo (DEBUG) ativo para `<logs_dir>/<run_id>/pipeline.log`.

    `logs_dir` é recebido explicitamente (não lido de `config.settings` aqui
    dentro) para que os testes possam apontar para `tmp_path` sem sujar o
    `data/logs/` real -- mesmo padrão já usado por `ModelingConfig.checkpoints_dir`
    e pelos `gold_*_path` de teste.

    Remove o handler do `run_id` anterior (se houver) do logger raiz e do
    logger interno do BERTopic antes de anexar o novo -- ver ADR 0015, decisão
    5 (log por `run_id` é trocado, não acumulado).

    O BERTopic anexa seu próprio `StreamHandler` a `logging.getLogger("BERTopic")`
    e desliga `propagate` ao se configurar (`bertopic/_bertopic.py`), então suas
    mensagens de sub-etapa (embedding/dimensionalidade/clustering/representação)
    só chegam a um arquivo nosso se anexarmos o handler diretamente nesse logger.
    """
    global _current_run_file_handler

    bertopic_logger = logging.getLogger("BERTopic")
    root = logging.getLogger()
    # Independente de `configure_console_logging` já ter rodado ou não --
    # quem chama isto direto (ex: run_deterministic_modeling, usado por
    # testes e pelo notebook sem nenhum setup de console) ainda precisa que
    # os registros DEBUG/INFO cheguem ao handler de arquivo.
    root.setLevel(logging.DEBUG)

    if _current_run_file_handler is not None:
        root.removeHandler(_current_run_file_handler)
        bertopic_logger.removeHandler(_current_run_file_handler)
        _current_run_file_handler.close()

    log_dir = logs_dir / run_id
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))

    root.addHandler(file_handler)
    bertopic_logger.addHandler(file_handler)

    _current_run_file_handler = file_handler
