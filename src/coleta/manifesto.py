"""
Manifesto de um Snapshot local (ADR 0039, issue #247): o arquivo `manifesto.json`
que diz o que uma Coleta cobre sem precisar baixá-la.

Só contagens, datas e identificadores técnicos (tag, usernames públicos dos
governadores). Nunca nomes de pessoas, textos de comentários/legendas nem
segredos: o conteúdo é montado só a partir de contagens agregadas, e
`validar_manifesto` recusa qualquer campo fora do esquema.

Sem rede e sem relógio implícito: data/hora da extração, versão do código e
custo real entram como argumento.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from deltalake import DeltaTable

from src.coleta.recorte import Recorte, tag_valida

VERSAO_ESQUEMA = 3
# v1 não tem `recorte_efetivo`; v1 e v2 gravam todas as chaves de `recorte`, com nulo onde não se aplicam;
# a v3 só grava as que se aplicam (sem nulos).
VERSOES_ACEITAS = (1, 2, VERSAO_ESQUEMA)
NOME_ARQUIVO = "manifesto.json"
FONTES = ("posts", "reels", "perfis", "ugc")
CAMADAS = ("bronze", "silver", "gold")

# fonte -> (tabela Bronze, coluna de perfil, coluna de data) para a cobertura. Posts, reels e UGC usam a data de
# publicação (`timestamp`, UTC); perfis não têm publicação, então a data é a da captura (`_ingested_at`).
_BRONZE = {
    "posts": ("instagram_posts", "ownerUsername", "timestamp"),
    "reels": ("instagram_reels", "ownerUsername", "timestamp"),
    "perfis": ("instagram_profiles", None, "_ingested_at"),
    "ugc": ("ugc_mentions", None, "timestamp"),
}
# UGC por perfil vem da Silver, onde o post de terceiro já foi correlacionado a
# um governador (`governor_username`); o autor do post (pessoa) nunca entra.
_UGC_SILVER = ("ugc_mentions", "governor_username", "data_hora")


def versao_do_codigo(repo: Path | str | None = None) -> str:
    """Hash git curto do código em uso; `desconhecida` fora de um repositório."""
    try:
        saida = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=str(repo) if repo else None,
            capture_output=True,
            text=True,
            check=True,
        )
        return saida.stdout.strip() or "desconhecida"
    except (OSError, subprocess.CalledProcessError):
        return "desconhecida"


def _ler(caminho: Path, colunas: list[str] | None = None) -> pd.DataFrame | None:
    if not (caminho / "_delta_log").is_dir():
        return None
    tabela = DeltaTable(str(caminho)).to_pyarrow_table(columns=colunas)
    return tabela.to_pandas()


def _datas(serie: pd.Series) -> tuple[str | None, str | None]:
    datas = pd.to_datetime(serie, errors="coerce", utc=True).dropna()
    if datas.empty:
        return None, None
    return datas.min().date().isoformat(), datas.max().date().isoformat()


def _cobertura(df: pd.DataFrame | None, col_perfil: str | None, col_data: str | None) -> dict[str, Any]:
    if df is None:
        return {"itens": 0, "mais_antiga": None, "mais_recente": None, "por_perfil": []}
    mais_antiga, mais_recente = _datas(df[col_data]) if col_data else (None, None)
    por_perfil: list[dict[str, Any]] = []
    if col_perfil:
        validos = df[df[col_perfil].notna()]
        for username, grupo in sorted(validos.groupby(col_perfil), key=lambda kv: str(kv[0])):
            antiga, recente = _datas(grupo[col_data]) if col_data else (None, None)
            por_perfil.append(
                {"username": str(username), "itens": len(grupo), "mais_antiga": antiga, "mais_recente": recente}
            )
    return {"itens": len(df), "mais_antiga": mais_antiga, "mais_recente": mais_recente, "por_perfil": por_perfil}


def _tabelas(data_dir: Path) -> list[dict[str, Any]]:
    tabelas: list[dict[str, Any]] = []
    for camada in CAMADAS:
        pasta = data_dir / camada
        if not pasta.is_dir():
            continue
        for t in sorted(pasta.iterdir()):
            if (t / "_delta_log").is_dir():
                linhas = DeltaTable(str(t)).to_pyarrow_dataset().count_rows()
                tabelas.append({"camada": camada, "nome": t.name, "linhas": int(linhas)})
    return tabelas


def _recorte_pedido(recorte: Recorte) -> dict[str, Any]:
    """O que foi pedido, só com as chaves que se aplicam (a janela efetiva vai em `recorte_efetivo`)."""
    pedido: dict[str, Any] = {
        "dias": recorte.dias,
        "inicio": recorte.inicio.isoformat() if recorte.inicio else None,
        "fim": recorte.fim.isoformat() if recorte.fim else None,
        "teto": recorte.teto,
    }
    return {k: v for k, v in pedido.items() if v is not None}


def gerar_manifesto(
    data_dir: Path | str,
    *,
    tag: str,
    recorte: Recorte,
    extraido_em: datetime,
    versao_codigo: str,
    custo_estimado: dict[str, float] | None = None,
    custo_real: float | dict[str, float] | None = None,
) -> dict[str, Any]:
    """Monta e valida o manifesto do Snapshot em `data_dir` (`bronze/`, `silver/`, `gold/`)."""
    base = Path(data_dir)
    cobertura: dict[str, Any] = {}
    for fonte, (tabela, col_perfil, col_data) in _BRONZE.items():
        cobertura[fonte] = _cobertura(_ler(base / "bronze" / tabela), col_perfil, col_data)
    silver_tabela, silver_perfil, silver_data = _UGC_SILVER
    silver_ugc = _ler(base / "silver" / silver_tabela, [silver_perfil, silver_data])
    if silver_ugc is not None:
        cobertura["ugc"]["por_perfil"] = _cobertura(silver_ugc, silver_perfil, silver_data)["por_perfil"]

    janela = recorte.janela_efetiva(extraido_em.date())
    manifesto = {
        "versao_esquema": VERSAO_ESQUEMA,
        "identidade": {
            "tag": tag,
            "extraido_em": extraido_em.isoformat(timespec="seconds"),
            "versao_codigo": versao_codigo,
        },
        "recorte": _recorte_pedido(recorte),
        "recorte_efetivo": (
            {"inicio": janela[0].isoformat(), "fim": janela[1].isoformat()} if janela else None
        ),
        "cobertura": cobertura,
        "custo": {
            "estimado": dict(custo_estimado) if custo_estimado is not None else None,
            "real": dict(custo_real) if isinstance(custo_real, dict) else custo_real,
        },
        "tabelas": _tabelas(base),
    }
    validar_manifesto(manifesto)
    return manifesto


def escrever_manifesto(data_dir: Path | str, manifesto: dict[str, Any]) -> Path:
    """Grava `<data_dir>/manifesto.json` (UTF-8, indentado)."""
    validar_manifesto(manifesto)
    destino = Path(data_dir) / NOME_ARQUIVO
    destino.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destino


# --- esquema -----------------------------------------------------------------


def _exigir(cond: bool, caminho: str, msg: str) -> None:
    if not cond:
        raise ValueError(f"Manifesto inválido em {caminho}: {msg}")


def _chaves(obj: Any, esperadas: set[str], caminho: str) -> dict:
    _exigir(isinstance(obj, dict), caminho, "esperado objeto")
    _exigir(set(obj) == esperadas, caminho, f"chaves {sorted(obj)} != {sorted(esperadas)}")
    return obj


def _int(v: Any, caminho: str, minimo: int = 0) -> None:
    _exigir(isinstance(v, int) and not isinstance(v, bool) and v >= minimo, caminho, f"inteiro >= {minimo}")


def _numero(v: Any, caminho: str) -> None:
    _exigir(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0, caminho, "número >= 0")


def _data_opcional(v: Any, caminho: str) -> None:
    if v is None:
        return
    _exigir(isinstance(v, str), caminho, "data ISO ou nulo")
    try:
        date.fromisoformat(v)
    except ValueError:
        _exigir(False, caminho, f"data inválida {v!r}")


def _intervalo(obj: dict, caminho: str) -> None:
    _int(obj["itens"], f"{caminho}.itens")
    _data_opcional(obj["mais_antiga"], f"{caminho}.mais_antiga")
    _data_opcional(obj["mais_recente"], f"{caminho}.mais_recente")
    if obj["mais_antiga"] and obj["mais_recente"]:
        _exigir(obj["mais_antiga"] <= obj["mais_recente"], caminho, "mais_antiga depois de mais_recente")


def validar_manifesto(m: Any) -> None:
    """Levanta `ValueError` se `m` não segue o esquema (chaves exatas, tipos,
    datas ISO). Esquema fechado: um campo extra (p.ex. texto) é recusado."""
    _exigir(isinstance(m, dict), "manifesto", "esperado objeto")
    v_esquema = m.get("versao_esquema")
    _exigir(v_esquema in VERSOES_ACEITAS, "versao_esquema", f"esperado um de {VERSOES_ACEITAS}")
    chaves = {"versao_esquema", "identidade", "recorte", "cobertura", "custo", "tabelas"}
    m = _chaves(m, chaves | ({"recorte_efetivo"} if v_esquema >= 2 else set()), "manifesto")
    v3 = v_esquema >= 3

    ident = _chaves(m["identidade"], {"tag", "extraido_em", "versao_codigo"}, "identidade")
    _exigir(isinstance(ident["tag"], str) and tag_valida(ident["tag"]), "identidade.tag", "tag fora da gramática")
    try:
        datetime.fromisoformat(ident["extraido_em"])
    except (TypeError, ValueError):
        _exigir(False, "identidade.extraido_em", "data e hora ISO")
    versao = ident["versao_codigo"]
    _exigir(
        isinstance(versao, str) and bool(versao) and versao.isascii() and " " not in versao,
        "identidade.versao_codigo",
        "hash sem espaços",
    )

    chaves_recorte = {"dias", "inicio", "fim", "teto"}
    if v3:  # só as chaves que se aplicam, nunca nulas
        _exigir(isinstance(m["recorte"], dict), "recorte", "esperado objeto")
        _exigir(set(m["recorte"]) <= chaves_recorte, "recorte", f"chaves {sorted(m['recorte'])} fora de {sorted(chaves_recorte)}")
        _exigir(all(v is not None for v in m["recorte"].values()), "recorte", "v3 não grava chave nula")
        rec = {k: m["recorte"].get(k) for k in chaves_recorte}
    else:
        rec = _chaves(m["recorte"], chaves_recorte, "recorte")
    for k in ("dias", "teto"):
        if rec[k] is not None:
            _int(rec[k], f"recorte.{k}", 1)
    _data_opcional(rec["inicio"], "recorte.inicio")
    _data_opcional(rec["fim"], "recorte.fim")
    if "recorte_efetivo" in m:
        ef = m["recorte_efetivo"]
        if ef is not None:
            ef = _chaves(ef, {"inicio", "fim"}, "recorte_efetivo")
            for k in ("inicio", "fim"):
                _exigir(ef[k] is not None, f"recorte_efetivo.{k}", "data ISO obrigatória")
                _data_opcional(ef[k], f"recorte_efetivo.{k}")
            _exigir(ef["inicio"] <= ef["fim"], "recorte_efetivo", "inicio depois de fim")

    cob = _chaves(m["cobertura"], set(FONTES), "cobertura")
    for fonte in FONTES:
        c = _chaves(cob[fonte], {"itens", "mais_antiga", "mais_recente", "por_perfil"}, f"cobertura.{fonte}")
        _intervalo(c, f"cobertura.{fonte}")
        _exigir(isinstance(c["por_perfil"], list), f"cobertura.{fonte}.por_perfil", "esperado lista")
        for i, p in enumerate(c["por_perfil"]):
            caminho = f"cobertura.{fonte}.por_perfil[{i}]"
            p = _chaves(p, {"username", "itens", "mais_antiga", "mais_recente"}, caminho)
            _exigir(isinstance(p["username"], str) and bool(p["username"]), f"{caminho}.username", "texto")
            _intervalo(p, caminho)

    custo = _chaves(m["custo"], {"estimado", "real"}, "custo")
    if custo["estimado"] is not None:
        _exigir(isinstance(custo["estimado"], dict), "custo.estimado", "objeto de números")
        for k, v in custo["estimado"].items():
            _exigir(isinstance(k, str), "custo.estimado", "chave texto")
            _numero(v, f"custo.estimado.{k}")
    if isinstance(custo["real"], dict):  # por actor (esquema novo); número ou nulo = Coletas antigas
        for k, v in custo["real"].items():
            _exigir(isinstance(k, str), "custo.real", "chave texto")
            _numero(v, f"custo.real.{k}")
    elif custo["real"] is not None:
        _numero(custo["real"], "custo.real")

    _exigir(isinstance(m["tabelas"], list), "tabelas", "esperado lista")
    for i, t in enumerate(m["tabelas"]):
        caminho = f"tabelas[{i}]"
        t = _chaves(t, {"camada", "nome", "linhas"}, caminho)
        _exigir(t["camada"] in CAMADAS, f"{caminho}.camada", f"uma de {CAMADAS}")
        _exigir(isinstance(t["nome"], str) and bool(t["nome"]), f"{caminho}.nome", "texto")
        _int(t["linhas"], f"{caminho}.linhas")
