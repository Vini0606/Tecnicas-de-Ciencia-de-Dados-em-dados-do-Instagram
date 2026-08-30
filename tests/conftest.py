import logging

import pytest


@pytest.fixture(autouse=True)
def _reset_logging_state():
    """`src.logging_setup.attach_run_log_handler` muta o logger raiz e o
    logger nomeado "BERTopic" globalmente (ver ADR 0015) -- sem limpeza, um
    handler de arquivo apontando pro `tmp_path` de um teste vazaria pros
    testes seguintes."""
    root = logging.getLogger()
    bertopic_logger = logging.getLogger("BERTopic")
    root_handlers_antes = list(root.handlers)
    bertopic_handlers_antes = list(bertopic_logger.handlers)

    yield

    for handler in list(root.handlers):
        if handler not in root_handlers_antes:
            root.removeHandler(handler)
            handler.close()
    for handler in list(bertopic_logger.handlers):
        if handler not in bertopic_handlers_antes:
            bertopic_logger.removeHandler(handler)
            handler.close()

    import src.logging_setup as logging_setup

    logging_setup._current_run_file_handler = None
