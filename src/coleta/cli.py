"""
Linha de comando da Coleta (ADR 0039, issue #252): o caminho unico para extrair,
publicar, restaurar, listar e baixar Coletas.

    uv run python coleta.py coletar --dias 90 --teto 250 --destino <pasta limpa>       # so mostra o custo
    uv run python coleta.py coletar --dias 90 --teto 250 --destino <pasta limpa> --yes # gasta na Apify
    uv run python coleta.py publicar <pasta> [--rotulo piloto] [--yes]
    uv run python coleta.py restaurar <tag> [--rotulo restaurada] [--yes]
    uv run python coleta.py listar
    uv run python coleta.py baixar <tag> --destino <pasta>

Sem `--yes` nada e gasto na Apify nem enviado ao HF: o comando mostra a estimativa
de custo (coletar) ou o plano exato (publicar, restaurar) e termina. A modelagem
pesada continua local: `coletar --modelar` roda so o estagio deterministico.

Tudo que e externo (Apify, HF, relogio, planilha de governadores) entra por
argumento de `main`, entao os testes nunca usam rede nem gastam.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Mapping
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from config import settings
from src.coleta import hf
from src.coleta.calibracao import Calibracao, carregar_calibracao
from src.coleta.coletar import ColetaNaoConfirmada, coletar, criar_scraper
from src.coleta.custo import PLANO_PADRAO, estimar_custo, teto_e_padrao, teto_efetivo
from src.coleta.recorte import Recorte
from src.run_id import build_run_id

ClienteFactory = Callable[[], "hf.ClienteColetaHF"]
ScraperFactory = Callable[[Recorte, date], object]


def _data(valor: str) -> date:
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise argparse.ArgumentTypeError(f"data invalida {valor!r}: use AAAA-MM-DD") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coleta", description="Coleta: extrai, publica, restaura, lista e baixa Snapshots."
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    c = sub.add_parser("coletar", help="extrai um Recorte da Apify para uma pasta limpa")
    c.add_argument("--dias", type=int, help="janela relativa: ultimos N dias")
    c.add_argument("--inicio", type=_data, help="inicio do intervalo absoluto (AAAA-MM-DD)")
    c.add_argument("--fim", type=_data, help="fim do intervalo absoluto (AAAA-MM-DD)")
    c.add_argument("--teto", type=int, help="teto de itens por perfil em cada colecao")
    c.add_argument("--rotulo", help="rotulo opcional da tag (minusculas, digitos, '-')")
    c.add_argument("--destino", required=True, type=Path, help="pasta de dados LIMPA (nunca a data/ em uso)")
    c.add_argument(
        "--yes",
        action="store_true",
        help="confirma o gasto real na Apify; sem isso so mostra a estimativa",
    )
    c.add_argument(
        "--modelar",
        action="store_true",
        help="roda tambem o estagio deterministico de modelagem (pesado; exige DATA_DIR=<destino>)",
    )
    c.add_argument(
        "--sem-calibracao",
        action="store_true",
        help="estima com as taxas fixas da ADR 0012, sem consultar a Coleta vigente no HF (offline)",
    )

    p = sub.add_parser("publicar", help="publica um Snapshot local no HF como a Coleta vigente")
    p.add_argument("snapshot", type=Path, help="pasta do Snapshot (com manifesto.json)")
    p.add_argument("--rotulo", help="rotulo novo para o identificador (padrao: o do manifesto)")
    p.add_argument("--limite-bytes", type=int, default=None, help="limite de armazenamento do dataset")
    p.add_argument("--yes", action="store_true", help="confirma o envio; sem isso so mostra o plano")

    r = sub.add_parser("restaurar", help="traz uma Coleta antiga de volta para a main (novo commit)")
    r.add_argument("tag", metavar="coleta", help="identificador coleta_*, tag de uso ou hash de commit")
    r.add_argument("--rotulo", default=hf.ROTULO_RESTAURADA)
    r.add_argument("--limite-bytes", type=int, default=None)
    r.add_argument("--yes", action="store_true", help="confirma; sem isso so mostra o plano")

    sub.add_parser("listar", help="lista as Coletas disponiveis no HF")

    b = sub.add_parser("baixar", help="baixa o Snapshot de uma Coleta")
    b.add_argument("tag", metavar="coleta", help="identificador coleta_*, tag de uso ou hash de commit")
    b.add_argument("--destino", required=True, type=Path)
    return parser


def _carregar_governadores() -> tuple[list[str], list[str], pd.DataFrame]:
    from scripts.apify_backfill_shared import load_governor_usernames, load_links

    return load_links(), load_governor_usernames(), pd.read_excel(settings.GOVERNADORES_FILE)


def _scraper_real(env: Mapping[str, str]) -> ScraperFactory:
    def fabrica(recorte: Recorte, hoje: date):
        token = env.get("APIFY_API_TOKEN")
        if not token:
            raise SystemExit("[ERRO] APIFY_API_TOKEN nao encontrado no ambiente/.env.")
        from apify_client import ApifyClient

        return criar_scraper(ApifyClient(token), recorte, hoje)

    return fabrica


def _modelar_callback(run_id: str) -> Callable[[dict[str, pd.DataFrame]], None]:
    def modelar(tabelas: dict[str, pd.DataFrame]) -> None:
        # So o estagio deterministico. O refinamento via Gemini e manual
        # (scripts/refine_topics.py, ADR 0001) e nunca roda daqui.
        from src.modeling.config import ModelingConfig
        from src.modeling.orchestration import run_deterministic_modeling

        post_comments = tabelas["post_comments"]
        resultado = run_deterministic_modeling(
            tabelas["reels"],
            tabelas["comments"],
            tabelas["posts"],
            tabelas["engagement"],
            ModelingConfig(),
            parent_run_id=run_id,
            df_post_comments=None if post_comments.empty else post_comments,
        )
        print(f"[MODELAGEM] Concluida com run_id: {resultado.run_id}")

    return modelar


def _milhar(valor: float) -> str:
    return f"{valor:,.0f}".replace(",", ".")


def _decimal(valor: float, casas: int) -> str:
    """Milhar com ponto e decimal com virgula (6500.5 -> '6.500,5')."""
    return f"{valor:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _usd(valor: float) -> str:
    return _decimal(valor, 2)


def _descrever_recorte(recorte: Recorte, teto: int) -> str:
    if recorte.dias is not None:
        janela = f"ultimos {recorte.dias} dias"
    elif recorte.inicio is not None:
        janela = f"de {recorte.inicio} a {recorte.fim}"
    else:
        janela = "so teto"
    padrao = " (teto padrao)" if teto_e_padrao(recorte) else ""
    return f"{janela}, ate {_milhar(teto)} itens por perfil e colecao{padrao}"


def formatar_estimativa(
    recorte: Recorte,
    hoje: date,
    n_governadores: int,
    plano: str,
    custo: dict[str, float],
    calibracao: Calibracao | None = None,
) -> str:
    """Texto da estimativa de `coletar`: cabecalho do Recorte e tabela por colecao (so ASCII,
    para o console do Windows)."""
    teto = teto_efetivo(recorte, hoje)
    janela = recorte.janela_efetiva(hoje)
    linhas = ["ESTIMATIVA DE CUSTO DA COLETA", ""]
    cabecalho = [("Recorte", _descrever_recorte(recorte, teto))]
    if janela:
        aproximada = " (aproximada)" if recorte.dias is not None else ""
        cabecalho.append(("Janela", f"{janela[0]} a {janela[1]}{aproximada}"))
    cabecalho += [("Governadores", str(n_governadores)), ("Plano Apify", plano)]
    calibracao = calibracao or Calibracao.sem_calibracao("calibracao nao usada", n_governadores)
    cabecalho.append(("Calibracao", calibracao.resumo()))
    linhas += [f"  {nome:<14}{valor}" for nome, valor in cabecalho]
    linhas.append(f"  {'':<14}{calibracao.detalhe()}")
    if teto_e_padrao(recorte):
        linhas += [
            "",
            f"  [AVISO] Sem --teto: usando o teto padrao de {_milhar(teto)} por perfil e por colecao.",
            f"          Pior caso ate US$ {_usd(custo['pior_caso_total'])}. Informe --teto para limitar o gasto.",
        ]

    cheio = n_governadores * teto
    tabela = [
        ("Colecao", "Resultados (esp. / pior)", "Esperado (US$)", "Pior caso (US$)"),
        ("Posts", f"{_milhar(custo['resultados_posts'])} / {_milhar(cheio)}", _usd(custo["posts"]), _usd(custo["pior_caso_posts"])),
        ("Reels", f"{_milhar(custo['resultados_reels'])} / {_milhar(cheio)}", _usd(custo["reels"]), _usd(custo["pior_caso_reels"])),
        ("UGC *", f"{_milhar(custo['resultados_ugc'])} / {_milhar(cheio)}", _usd(custo["ugc"]), _usd(custo["pior_caso_ugc"])),
        ("Perfis", f"{_milhar(n_governadores)} / {_milhar(n_governadores)}", _usd(custo["perfis"]), _usd(custo["pior_caso_perfis"])),
    ]
    larguras = [max(len(linha[i]) for linha in tabela) for i in range(4)]

    def formatar(linha: tuple[str, ...]) -> str:
        return "  " + "   ".join(
            (celula.ljust(larguras[i]) if i == 0 else celula.rjust(larguras[i])) for i, celula in enumerate(linha)
        )

    separador = "  " + "   ".join("-" * largura for largura in larguras)
    total = ("Total", "", _usd(custo["total"]), _usd(custo["pior_caso_total"]))
    linhas += ["", formatar(tabela[0]), separador, *map(formatar, tabela[1:]), separador, formatar(total), ""]
    linhas.append("  * UGC sem calibracao: assume o teto cheio em todos os perfis.")
    if custo["total"] == custo["pior_caso_total"]:
        linhas.append("  Esperado e pior caso coincidem: o teto vale em todas as colecoes.")
    return "\n".join(linhas)


def _com_sinal(valor: float, fmt: str) -> str:
    return ("+" if valor > 0 else "") + fmt


def formatar_comparacao(estimado: dict[str, float], real: dict[str, float] | None) -> str:
    """Tabela estimado (esperado) x real por coleção, ao fim de `coletar --yes` (so ASCII)."""
    if real is None:
        return "Custo real indisponivel: a Apify nao devolveu o custo de alguma chamada (manifesto com custo.real nulo)."
    linhas = [("Colecao", "Estimado (US$)", "Real (US$)", "Dif. (US$)", "Dif. (%)")]
    for nome, chave in (("Posts", "posts"), ("Reels", "reels"), ("UGC", "ugc"), ("Perfis", "perfis"), ("Total", "total")):
        est, rea = estimado[chave], real[chave]
        dif = rea - est
        pct = _com_sinal(dif, _decimal(dif / est * 100, 1) + "%") if est else "-"
        linhas.append((nome, _usd(est), _usd(rea), _com_sinal(dif, _usd(dif)), pct))
    larguras = [max(len(linha[i]) for linha in linhas) for i in range(5)]

    def formatar(linha: tuple[str, ...]) -> str:
        return "  " + "   ".join(
            (c.ljust(larguras[i]) if i == 0 else c.rjust(larguras[i])) for i, c in enumerate(linha)
        )

    separador = "  " + "   ".join("-" * largura for largura in larguras)
    corpo = [formatar(linhas[0]), separador, *map(formatar, linhas[1:5]), separador, formatar(linhas[5])]
    return "\n".join(["", "CUSTO ESTIMADO x REAL", "", *corpo])


def _cmd_coletar(args, scraper_factory: ScraperFactory, agora: datetime, cliente_factory: ClienteFactory) -> int:
    recorte = Recorte(dias=args.dias, inicio=args.inicio, fim=args.fim, teto=args.teto)
    hoje = agora.date()
    destino: Path = args.destino
    if destino.exists() and any(destino.iterdir()):
        print(f"[ERRO] A pasta {destino} nao esta vazia: extraia sempre em pasta de dados limpa.", file=sys.stderr)
        return 2
    if args.modelar and destino.resolve() != Path(settings.DATA_DIR).resolve():
        print(
            "[ERRO] --modelar grava checkpoints e Gold de modelagem em DATA_DIR: rode com "
            f"DATA_DIR={destino} no ambiente (ou sem --modelar).",
            file=sys.stderr,
        )
        return 2

    plano = os.environ.get("APIFY_PLAN", PLANO_PADRAO).upper()
    links, usernames, df_governadores = _carregar_governadores()
    if args.sem_calibracao:
        calibracao = Calibracao.sem_calibracao("calibracao desligada (--sem-calibracao)", len(usernames))
    else:
        calibracao = carregar_calibracao(cliente_factory, usernames)
    try:
        custo = estimar_custo(recorte, len(links), hoje, plano, calibracao)
    except ValueError as erro:
        print(f"[ERRO] {erro} (variavel APIFY_PLAN).", file=sys.stderr)
        return 2
    print(formatar_estimativa(recorte, hoje, len(links), plano, custo, calibracao))

    def confirmar(_custo: float) -> bool:
        if not args.yes:
            print("[ABORTADO] Nada foi gasto. Rode de novo com --yes para extrair de verdade na Apify.")
        return args.yes

    run_id = build_run_id()
    try:
        resultado = coletar(
            recorte,
            destino,
            scraper=scraper_factory(recorte, hoje) if args.yes else None,
            links=links,
            governor_usernames=usernames,
            df_governadores=df_governadores,
            confirmar=confirmar,
            hoje=hoje,
            agora=agora,
            rotulo=args.rotulo,
            run_id=run_id,
            modelar=_modelar_callback(run_id) if args.modelar else None,
            plano=plano,
            calibracao=calibracao,
        )
    except ColetaNaoConfirmada:
        return 0 if not args.yes else 1
    print(f"[OK] Coleta {resultado.tag} gravada em {resultado.destino} (run_id {resultado.run_id}).")
    print(formatar_comparacao(resultado.custo_estimado, resultado.custo_real))
    print(f"Proximo passo: coleta.py publicar {resultado.destino}")

    if args.modelar:
        from src.pipeline_report import relatorio_final

        return relatorio_final(agora, True, resultado.run_id, settings.LOGS_DIR)
    return 0


def _confirmar_plano(yes: bool) -> Callable[[hf.Plano], bool]:
    def confirmar(plano: hf.Plano) -> bool:
        print(plano.descrever())
        if not yes:
            print("(nada foi enviado; use --yes para confirmar)")
        return yes

    return confirmar


def main(
    argv: list[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    cliente_factory: ClienteFactory | None = None,
    scraper_factory: ScraperFactory | None = None,
    agora: datetime | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    env = os.environ if env is None else env
    cliente_factory = cliente_factory or hf.ClienteColetaHFReal
    agora = agora or datetime.now(timezone.utc)
    try:
        if args.comando == "coletar":
            return _cmd_coletar(args, scraper_factory or _scraper_real(env), agora, cliente_factory)
        cliente = cliente_factory()
        if args.comando == "publicar":
            resultado = hf.publicar(
                args.snapshot,
                args.rotulo,
                cliente=cliente,
                confirmar=_confirmar_plano(args.yes),
                limite_bytes=args.limite_bytes,
            )
            if resultado.publicado:
                print(f"[OK] Publicada a Coleta {resultado.coleta} (commit {resultado.commit}).")
        elif args.comando == "restaurar":
            resultado = hf.restaurar(
                args.tag,
                cliente=cliente,
                confirmar=_confirmar_plano(args.yes),
                rotulo=args.rotulo,
                limite_bytes=args.limite_bytes,
            )
            if resultado.publicado:
                print(f"[OK] Coleta {args.tag} restaurada na main como {resultado.coleta} (commit {resultado.commit}).")
        elif args.comando == "listar":
            for c in hf.listar(cliente=cliente):
                usos = ",".join(c.tags_de_uso)
                print(f"{c.coleta}\t{c.commit[:8]}\t{c.extraido_em.isoformat()}\t{c.recorte}\t{usos}")
        elif args.comando == "baixar":
            pasta = hf.baixar(args.tag, args.destino, cliente=cliente)
            print(f"[OK] Coleta {args.tag} baixada em {pasta}.")
    except (hf.ErroColetaHF, ValueError) as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 1
    return 0


def executar() -> None:
    from dotenv import load_dotenv

    from src.logging_setup import configure_console_logging

    load_dotenv()
    configure_console_logging()
    sys.exit(main())
