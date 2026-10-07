"""
Leva `data/landing/` e `data/bronze/` entre máquinas por um dataset privado
no Hugging Face (ADR 0035, issue #232). Silver, Gold, checkpoints e logs
nunca sobem nem são tocados: se regeneram com `pipeline.py --run-modeling`.

Credenciais no `.env`: `HF_TOKEN` (fine-grained, só esse dataset) e
`HF_DATASET_REPO` (`<usuario>/<nome>`).

Uso:
    uv run python scripts/sync_dados_hf.py push            # mostra o plano
    uv run python scripts/sync_dados_hf.py push --yes      # envia (máquina que coletou)
    uv run python scripts/sync_dados_hf.py pull            # baixa (outra máquina)
    uv run python scripts/sync_dados_hf.py pull --revisao <commit>
    uv run python scripts/sync_dados_hf.py pull --force    # sobrescreve dado local não enviado
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from config import settings
from src.dados_hf import (
    PADROES_SYNC,
    ClienteHF,
    ClienteHFReal,
    ErroHF,
    descrever_plano,
    inventario_de_caminhos,
    inventario_local,
    mensagem_de_commit,
    planejar_pull,
    planejar_push,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sincroniza landing + Bronze com o dataset privado do HF.")
    sub = parser.add_subparsers(dest="comando", required=True)

    push = sub.add_parser("push", help="envia landing e Bronze novas (máquina que coletou)")
    push.add_argument("--yes", action="store_true", help="confirma o envio; sem isso só mostra o plano")

    pull = sub.add_parser("pull", help="baixa landing e Bronze do dataset")
    pull.add_argument("--revisao", default=None, help="commit/revisão do dataset a baixar")
    pull.add_argument("--force", action="store_true", help="sobrescreve dado local ainda não enviado")
    return parser


def _cliente_real(env: Mapping[str, str]) -> ClienteHF:
    token, repo = env.get("HF_TOKEN", ""), env.get("HF_DATASET_REPO", "")
    faltando = [n for n, v in (("HF_TOKEN", token), ("HF_DATASET_REPO", repo)) if not v]
    if faltando:
        raise ErroHF(f"variáveis ausentes no .env: {', '.join(faltando)}")
    return ClienteHFReal(repo, token)


def main(
    argv: list[str] | None = None,
    *,
    cliente_factory: Callable[[Mapping[str, str]], ClienteHF] = _cliente_real,
    env: Mapping[str, str] | None = None,
    data_dir: Path | None = None,
) -> int:
    args = build_arg_parser().parse_args(argv)
    data_dir = data_dir or settings.DATA_DIR
    env = os.environ if env is None else env

    try:
        cliente = cliente_factory(env)
        revisao = getattr(args, "revisao", None)
        remoto = inventario_de_caminhos(cliente.listar_arquivos(revisao))
        local = inventario_local(data_dir)

        if args.comando == "push":
            plano = planejar_push(local, remoto)
            print(descrever_plano("push", plano))
            if plano.recusa:
                return 1
            if plano.vazio or not args.yes:
                if not plano.vazio:
                    print("Nada foi enviado. Use --yes para confirmar.")
                return 0
            cliente.enviar(data_dir, plano.padroes, mensagem_de_commit(plano))
            print("push: enviado em um único commit.")
            return 0

        plano = planejar_pull(local, remoto, args.force)
        print(descrever_plano("pull", plano))
        if plano.recusa:
            return 1
        if not plano.vazio:
            cliente.baixar(data_dir, PADROES_SYNC, revisao)
            print(f"pull: baixado em {data_dir}.")
        return 0
    except ErroHF as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    load_dotenv()
    sys.exit(main())
