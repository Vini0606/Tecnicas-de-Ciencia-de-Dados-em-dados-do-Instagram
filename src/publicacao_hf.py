"""
Publicação das tabelas do dashboard (Silver + Gold) em um dataset privado do
Hugging Face, e download delas na inicialização do app (ADR 0036).

O dashboard lê `data/silver` e `data/gold`, que não vão para o git. Em um
deploy (Streamlit Community Cloud) esses diretórios chegam vazios; aqui eles
são baixados do dataset de publicação, separado do dataset da landing/Bronze
(`src/dados_hf.py`, ADR 0035) para que o token do app, só de leitura, nunca
alcance o dado bruto.

A lógica de decisão é pura (tabelas presentes, configuração), e o cliente HF é
injetável (o `ClienteHFReal` de `dados_hf`), então os testes não usam rede.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from src.dados_hf import ClienteHF, ClienteHFReal, ErroHF

PADROES_PUBLICACAO = ["silver/**", "gold/**", "manifesto.json"]  # manifesto: ADR 0039

# Tabela cuja presença indica que os dados do dashboard já estão no disco.
_TABELA_SENTINELA = Path("gold") / "governor_engagement" / "_delta_log"

VAR_TOKEN = "HF_TOKEN"
VAR_REPO = "HF_DATASET_REPO_PUBLICACAO"
# Sem dataset de publicação próprio, usa o mesmo da landing/Bronze (ADR 0036):
# o layout espelho não colide (`silver/`, `gold/` x `landing/`, `bronze/`).
VAR_REPO_PADRAO = "HF_DATASET_REPO"
# Tag ou commit do dataset a baixar; sem ela, a `main` (Coleta vigente, ADR 0039).
VAR_REVISAO = "HF_DATASET_REVISAO"


@dataclass(frozen=True)
class ConfigHF:
    token: str
    repo: str
    revisao: str | None = None


def configuracao_hf(*fontes: Mapping[str, object] | None) -> ConfigHF | None:
    """Primeira fonte (env, secrets...) com token e repositório. O repositório é
    `HF_DATASET_REPO_PUBLICACAO` se houver, senão `HF_DATASET_REPO`."""
    for fonte in fontes:
        if not fonte:
            continue
        token = str(fonte.get(VAR_TOKEN) or "").strip()
        repo = str(fonte.get(VAR_REPO) or fonte.get(VAR_REPO_PADRAO) or "").strip()
        if token and repo:
            revisao = str(fonte.get(VAR_REVISAO) or "").strip() or None
            return ConfigHF(token=token, repo=repo, revisao=revisao)
    return None


def dados_presentes(data_dir: Path | str) -> bool:
    """`True` se o Gold do dashboard já está em `data_dir`."""
    return (Path(data_dir) / _TABELA_SENTINELA).is_dir()


def tabelas_publicaveis(data_dir: Path | str) -> list[str]:
    """Tabelas Delta de Silver e Gold presentes em `data_dir` (`gold/<tabela>`)."""
    base = Path(data_dir)
    tabelas: list[str] = []
    for camada in ("silver", "gold"):
        pasta = base / camada
        if not pasta.is_dir():
            continue
        tabelas += [
            f"{camada}/{t.name}"
            for t in sorted(pasta.iterdir())
            if (t / "_delta_log").is_dir()
        ]
    return tabelas


def descrever_publicacao(tabelas: list[str]) -> str:
    if not tabelas:
        return "publicar: nada a enviar (nenhuma tabela Delta em data/silver ou data/gold)."
    return "publicar: plano\n" + "\n".join(f"  {t}" for t in tabelas)


def publicar(
    data_dir: Path | str,
    config: ConfigHF,
    cliente: ClienteHF | None = None,
    mensagem: str = "publicar: silver + gold do dashboard",
) -> list[str]:
    """Envia Silver e Gold. Recusa se não houver Gold (evita publicar um
    dataset que deixaria o app vazio)."""
    tabelas = tabelas_publicaveis(data_dir)
    if not any(t.startswith("gold/") for t in tabelas):
        raise ErroHF(
            "nenhuma tabela Gold em data/gold: rode a pipeline antes de publicar."
        )
    cliente = cliente or ClienteHFReal(config.repo, config.token)
    cliente.enviar(Path(data_dir), PADROES_PUBLICACAO, mensagem)
    return tabelas


def baixar(
    data_dir: Path | str,
    config: ConfigHF,
    cliente: ClienteHF | None = None,
) -> None:
    """Baixa Silver e Gold para `data_dir`, mantendo o layout espelho."""
    cliente = cliente or ClienteHFReal(config.repo, config.token)
    cliente.baixar(Path(data_dir), PADROES_PUBLICACAO, config.revisao)


def ler_manifesto(data_dir: Path | str) -> dict | None:
    """Manifesto do Snapshot baixado, ou `None` se ausente, ilegivel ou invalido.
    Nunca levanta: o app segue sem a indicacao da Coleta."""
    import json

    from src.coleta.manifesto import NOME_ARQUIVO, validar_manifesto

    try:
        m = json.loads((Path(data_dir) / NOME_ARQUIVO).read_text(encoding="utf-8"))
        validar_manifesto(m)
    except (OSError, ValueError):
        return None
    return m


def garantir_dados(
    data_dir: Path | str,
    config: ConfigHF | None,
    baixador: Callable[[Path | str, ConfigHF], None] = baixar,
) -> str:
    """Garante que os dados do dashboard estejam em `data_dir`. Devolve o
    estado: `local` (já havia), `baixado`, `sem_configuracao` (nada a fazer, o
    dashboard mostra o aviso de dados ausentes) ou `erro: <motivo>` (sem token)."""
    if dados_presentes(data_dir):
        return "local"
    if config is None:
        return "sem_configuracao"
    try:
        baixador(data_dir, config)
    except ErroHF as exc:
        return f"erro: {exc}"
    except Exception as exc:  # noqa: BLE001 - app não pode cair por falha de rede
        detalhe = str(exc).replace(config.token, "***")
        return f"erro: {type(exc).__name__}: {detalhe}"
    return (
        "baixado"
        if dados_presentes(data_dir)
        else "erro: o dataset não trouxe o Gold esperado."
    )
