"""
Publica `data/silver` e `data/gold` em um dataset privado do Hugging Face, de
onde o dashboard (Streamlit Cloud) baixa os dados na inicialização (ADR 0036).

Credenciais no `.env`: `HF_TOKEN` (escrita, só nesse dataset) e
`HF_DATASET_REPO_PUBLICACAO` (`<usuario>/<nome>`), um dataset DIFERENTE do da
landing/Bronze (`HF_DATASET_REPO`).

Uso:
    uv run python scripts/publicar_dashboard_hf.py          # mostra o plano
    uv run python scripts/publicar_dashboard_hf.py --yes    # envia
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from config import settings
from src.dados_hf import ErroHF
from src.publicacao_hf import (
    configuracao_hf,
    descrever_publicacao,
    publicar,
    tabelas_publicaveis,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publica Silver + Gold do dashboard no HF."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirma o envio; sem isso só mostra o plano",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    tabelas = tabelas_publicaveis(settings.DATA_DIR)
    print(descrever_publicacao(tabelas))
    if not args.yes:
        print("(nada foi enviado; use --yes para confirmar)")
        return 0

    config = configuracao_hf(os.environ)
    if config is None:
        print(
            "erro: defina HF_TOKEN e HF_DATASET_REPO_PUBLICACAO no .env",
            file=sys.stderr,
        )
        return 2
    try:
        enviadas = publicar(settings.DATA_DIR, config)
    except ErroHF as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    print(f"ok: {len(enviadas)} tabelas enviadas para {config.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
