"""Robustez do cruzamento sentimento x grupo de desempenho à composição de perfis (Seção 5.4.3 do TCC).

Uso, na raiz do repositório: python notebooks/modelagens/validacao_sentimento/robustez_por_perfil.py
Lê só a Gold e grava `robustez_por_perfil.json` (agregados, sem textos). Proporções sobre os comentários
classificados; IC de 95% por bootstrap de publicações (semente 42), porque comentários de uma mesma publicação
são dependentes. "Mesma mistura" é a negatividade do corpo de cada perfil, ponderada pelos comentários do perfil
no grupo comparado: o que se observaria se só a composição de perfis mudasse.
"""

import json
from pathlib import Path

import numpy as np
from deltalake import DeltaTable

PASTA = Path(__file__).resolve().parent
GOLD = PASTA.parents[2] / "data" / "gold"
PERFIL = "tarcisiogdf"
N_BOOT = 4000
MIN_COMENTARIOS = 30


def ler(nome):
    return DeltaTable(str(GOLD / nome)).to_pandas()


def ic(d, seed=42):
    g = d.groupby("id_reel")["neg"].agg(["sum", "size"]).to_numpy()
    rng = np.random.default_rng(seed)
    props = []
    for _ in range(N_BOOT):
        x = g[rng.integers(0, len(g), len(g))].sum(axis=0)
        props.append(x[0] / x[1] * 100)
    return [round(float(v), 1) for v in np.percentile(props, [2.5, 97.5])]


def resumo(d):
    return {
        "n": len(d),
        "publicacoes": int(d["id_reel"].nunique()),
        "perfis": int(d["u"].nunique()),
        "neg": round(float(d["neg"].mean() * 100), 1),
        "ic95": ic(d),
    }


def mesma_mistura(alvo, corpo):
    peso = alvo.groupby("u").size()
    base = corpo.groupby("u")["neg"].mean()
    return round(float((peso * base.reindex(peso.index)).sum() / peso.sum() * 100), 1)


def retirando_um(d, corpo):
    perfis = sorted(d["u"].unique())
    sem = {u: float(d[d["u"] != u]["neg"].mean() * 100) for u in perfis}
    dif = {u: sem[u] - float(corpo[corpo["u"] != u]["neg"].mean() * 100) for u in perfis}
    menor = min(dif, key=dif.get)
    return {
        "neg_min": round(min(sem.values()), 1),
        "neg_max": round(max(sem.values()), 1),
        "menor_diferenca_pp": round(dif[menor], 1),
        "perfil_da_menor_diferenca": menor,
    }


def dentro_dos_perfis(alvo, corpo):
    a = alvo.groupby("u")["neg"].agg(["size", "mean"])
    a = a[a["size"] >= MIN_COMENTARIOS]
    dif = (a["mean"] - corpo.groupby("u")["neg"].mean().reindex(a.index)) * 100
    return {"perfis": len(a), "mais_negativos": int((dif > 0).sum()), "mediana_pp": round(float(dif.median()), 1)}


s = ler("governor_sentiment")
c = s[(s["fonte"] == "comentario") & s["sentiment_label"].notna()].copy()
c["u"] = c["inputUrl"].str.extract(r"com/([^/?]+)")[0]
c["neg"] = (c["sentiment_label"] == "negative").astype(float)


def com_grupo(tabela):
    g = ler(tabela)
    chave = next(x for x in ("id_reel", "id_post", "id") if x in g.columns)
    return c.merge(g[[chave, "cluster_label"]].rename(columns={chave: "id_reel"}), on="id_reel")


r = com_grupo("governor_clusters_reels")
f = com_grupo("governor_clusters_posts")
f["faixa"] = f["cluster_label"].map(lambda x: "corpo" if x == 0 else "acima" if x in (7, 6, 10) else "excepcional")
saida = {}
conjuntos = {
    "reels": (r[r["cluster_label"] == 0], {"virais": r[r["cluster_label"] == 2]}),
    "feed": (
        f[f["faixa"] == "corpo"],
        {
            "acima": f[f["faixa"] == "acima"],
            "excepcional": f[f["faixa"] == "excepcional"],
            "acima_do_corpo": f[f["faixa"] != "corpo"],
        },
    ),
}
for nome, (corpo, alvos) in conjuntos.items():
    saida[nome] = {
        "corpo": resumo(corpo),
        "corpo_sem_tarcisio": resumo(corpo[corpo["u"] != PERFIL]),
        "corpo_so_tarcisio": resumo(corpo[corpo["u"] == PERFIL]),
    }
    for k, d in alvos.items():
        saida[nome][k] = {
            "todos": resumo(d),
            "sem_tarcisio": resumo(d[d["u"] != PERFIL]),
            "so_tarcisio": resumo(d[d["u"] == PERFIL]),
            "corpo_mesma_mistura": mesma_mistura(d, corpo),
            "retirando_um_perfil": retirando_um(d, corpo),
            "dentro_dos_perfis": dentro_dos_perfis(d, corpo),
        }
(PASTA / "robustez_por_perfil.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(saida, ensure_ascii=False, indent=1))
