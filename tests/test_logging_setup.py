import logging

from src.logging_setup import attach_run_log_handler, configure_console_logging


def test_attach_run_log_handler_cria_arquivo_dentro_do_run_id(tmp_path):
    attach_run_log_handler("run_a", tmp_path)

    logging.getLogger("algum.modulo").info("mensagem de teste")

    log_path = tmp_path / "run_a" / "pipeline.log"
    assert log_path.exists()
    assert "mensagem de teste" in log_path.read_text(encoding="utf-8")


def test_attach_run_log_handler_troca_nao_acumula(tmp_path):
    attach_run_log_handler("run_a", tmp_path)
    attach_run_log_handler("run_b", tmp_path)

    logging.getLogger("algum.modulo").info("so deve ir pro run_b")

    log_a = (tmp_path / "run_a" / "pipeline.log").read_text(encoding="utf-8")
    log_b = (tmp_path / "run_b" / "pipeline.log").read_text(encoding="utf-8")
    assert "so deve ir pro run_b" not in log_a
    assert "so deve ir pro run_b" in log_b


def test_attach_run_log_handler_captura_logger_do_bertopic(tmp_path):
    attach_run_log_handler("run_a", tmp_path)

    # .warning() porque o BERTopic (fora de um `BERTopic(verbose=True)` real)
    # configura seu logger em WARNING por padrão -- ver bertopic/_bertopic.py.
    logging.getLogger("BERTopic").warning("mensagem do bertopic")

    log_path = tmp_path / "run_a" / "pipeline.log"
    assert "mensagem do bertopic" in log_path.read_text(encoding="utf-8")


def test_configure_console_logging_e_idempotente():
    configure_console_logging()
    n_handlers_apos_primeira_chamada = len(
        [h for h in logging.getLogger().handlers if getattr(h, "_is_console_handler", False)]
    )

    configure_console_logging()
    n_handlers_apos_segunda_chamada = len(
        [h for h in logging.getLogger().handlers if getattr(h, "_is_console_handler", False)]
    )

    assert n_handlers_apos_primeira_chamada == 1
    assert n_handlers_apos_segunda_chamada == 1
