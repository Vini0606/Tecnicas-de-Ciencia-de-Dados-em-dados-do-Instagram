"""Consolida a camada 1 (anotacao) com as camadas 2 e 3 e gera a planilha de conferencia.
Uso: python consolidar.py <pasta_aval_topicos> <pasta_aval_metricas>"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, spearmanr
from sklearn.metrics import cohen_kappa_score

A, M = Path(sys.argv[1]), Path(sys.argv[2])
pd.set_option("display.width", 200, "display.max_columns", 30)


def carregar(modelo, lotes):
    linhas = []
    for i in range(1, lotes + 1):
        lote = {t["topico"]: t for t in json.loads((A / f"lote_{modelo}_{i}.json").read_text(encoding="utf-8"))}
        for a in json.loads((A / f"anotacao_{modelo}_{i}.json").read_text(encoding="utf-8")):
            t = lote[a["topico"]]
            linhas.append({**a, "lote": i, "n_docs_lidos": len(t["documentos"]),
                           "amostra_docs": " || ".join(d[:160].replace("\n", " ") for d in t["documentos"][:6])})
    d = pd.DataFrame(linhas)
    d["frac_fora"] = d.docs_fora / d.n_docs_lidos
    # coerencia derivada so da fracao de documentos fora, com os cortes da rubrica em proporcao a 15 (3/15 e 7/15)
    d["coerencia_derivada"] = np.select([d.frac_fora <= 3 / 15 + 1e-9, d.frac_fora <= 7 / 15 + 1e-9], [3, 2], 1)
    return d


def relatorio(modelo, d, met, peso_col):
    d = d.merge(met, on="topico", how="left")
    print(f"\n==================== {modelo}: {len(d)} topicos ====================")
    tot = d[peso_col].sum()
    for col in ("coerencia", "coerencia_derivada", "utilidade"):
        c = d[col].value_counts().reindex([1, 2, 3], fill_value=0)
        w = d.groupby(col)[peso_col].sum().reindex([1, 2, 3], fill_value=0) / tot * 100
        print(f"{col:19s} topicos 1/2/3 = {c[1]}/{c[2]}/{c[3]} | % do volume = {w[1]:.1f}/{w[2]:.1f}/{w[3]:.1f}")
    concord = (d.coerencia == d.coerencia_derivada).mean() * 100
    kappa = cohen_kappa_score(d.coerencia, d.coerencia_derivada, weights="linear")
    print(f"coerencia anotada x derivada: concordancia {concord:.0f}%, kappa ponderado {kappa:.2f}")
    print("por lote (media coerencia | derivada | utilidade | frac_fora | n):")
    print(d.groupby("lote").agg(coer=("coerencia", "mean"), deriv=("coerencia_derivada", "mean"),
                                util=("utilidade", "mean"), fora=("frac_fora", "mean"), n=("topico", "size")).round(2).to_string())
    print("anotada < derivada (anotador mais severo que a fracao de docs fora):", int((d.coerencia < d.coerencia_derivada).sum()),
          "| tipo_falha desses:", d[d.coerencia < d.coerencia_derivada].tipo_falha.value_counts().to_dict())
    print("tipo_falha:", d.tipo_falha.value_counts(dropna=False).to_dict())
    print("categoria:", d.categoria.value_counts().to_dict())
    print("alinhamento:", d.alinhamento_palavras_docs.value_counts().to_dict())
    print("rotulo Gemini:", d.rotulo_gemini_avaliacao.value_counts().to_dict(),
          "| rotulos repetidos (mesmo texto em 2+ topicos):",
          int(d.rotulo_gemini.duplicated(keep=False).sum()), "topicos em", int(d.rotulo_gemini[d.rotulo_gemini.duplicated()].nunique()), "textos")
    pequenos = d.n_docs_lidos < 15
    if pequenos.any():
        print(f"topicos com menos de 15 docs: {int(pequenos.sum())} | util media pequenos {d[pequenos].utilidade.mean():.2f} x grandes {d[~pequenos].utilidade.mean():.2f}"
              f" | coer media {d[pequenos].coerencia.mean():.2f} x {d[~pequenos].coerencia.mean():.2f}")
    print("Spearman (rho, p) entre metricas automaticas e julgamento:")
    for m in [c for c in d.columns if c.startswith("npmi_")] + [peso_col]:
        out = []
        for j in ("coerencia", "coerencia_derivada", "utilidade", "frac_fora"):
            r, p = spearmanr(d[m], d[j], nan_policy="omit")
            out.append(f"{j}={r:+.2f} ({p:.3f})")
        print(f"  {m:16s} " + "  ".join(out))
    a3 = d[d.coerencia == 3]["npmi_doc"]
    a1 = d[d.coerencia <= 2]["npmi_doc"]
    print(f"NPMI doc: coerencia 3 mediana {a3.median():+.3f} (n={len(a3)}) x coerencia 1-2 {a1.median():+.3f} (n={len(a1)}), "
          f"Mann-Whitney p={mannwhitneyu(a3, a1).pvalue:.3f}")
    return d


com = carregar("comentarios", 2)
leg = carregar("legendas", 6)
mc = pd.read_csv(M / "metricas_comentarios.csv")
# sentimento atual (Gold, classificador ajustado da ADR 0049), nao o do checkpoint de 18/11
_g = pd.read_parquet(M / "gold_sent.parquet")
_g = _g[_g.Topic != -1].groupby("Topic").sentiment_label.agg(
    pct_pos=lambda x: (x == "positive").mean() * 100, pct_neg=lambda x: (x == "negative").mean() * 100)
mc = mc.drop(columns=["pct_pos", "pct_neg"]).merge(_g.reset_index().rename(columns={"Topic": "topico"}), on="topico")
ml = pd.read_csv(M / "metricas_legendas.csv")
dc = relatorio("comentarios", com, mc.drop(columns=["palavras"]), "n_comentarios")
dl = relatorio("legendas", leg, ml.drop(columns=["palavras"]), "n_publicacoes")

print("\n=========== camada 2 x camada 1 ===========")
print("comentarios, sentimento por categoria (media dos topicos; % pos / % neg; n):")
print(dc.groupby("categoria").agg(pos=("pct_pos", "mean"), neg=("pct_neg", "mean"), n=("topico", "size"),
                                  coment=("n_comentarios", "sum")).round(1).to_string())
print("comentarios, concentracao por utilidade (medianas):")
print(dc.groupby("utilidade")[["pct_perfil_top", "pct_semana_top", "pct_repetidos", "comentarios_por_autor", "n_perfis"]].median().round(1).to_string())
print("legendas, concentracao por utilidade (medianas):")
print(dl.groupby("utilidade")[["pct_perfil_top", "pct_semana_top", "n_perfis", "n_publicacoes"]].median().round(1).to_string())

ordem = ["topico", "rotulo_gemini", "rotulo_proprio", "coerencia", "coerencia_derivada", "docs_fora", "n_docs_lidos", "tipo_falha",
         "alinhamento_palavras_docs", "utilidade", "categoria", "justificativa", "rotulo_gemini_avaliacao", "rotulo_gemini_obs",
         "npmi_doc", "npmi_janela10", "lote", "amostra_docs"]
with pd.ExcelWriter(A / "conferencia_topicos.xlsx") as xw:
    pd.DataFrame({"Instrucao": [
        "Anotacao por modelo de linguagem (Claude), as cegas quanto a tamanho, sentimento, perfil, NPMI e rotulo Gemini, sob a rubrica rubrica_topicos.md.",
        "Confira coerencia e utilidade de cada topico. Se concordar, marque S em 'confere'. Se discordar, preencha a nota corrigida e o motivo.",
        "coerencia_derivada e so a fracao de documentos fora com os cortes da rubrica; nao e julgamento, serve de checagem.",
        "amostra_docs mostra 6 dos 15 documentos lidos (cortados); os 15 completos estao em lote_<modelo>_<n>.json.",
        "Contem textos reais de comentarios e legendas: arquivo local, nao versionar."]}).to_excel(xw, sheet_name="Leia-me", index=False)
    for nome, d in (("comentarios", dc), ("legendas", dl)):
        extra = ["n_comentarios", "pct_pos", "pct_neg", "pct_perfil_top", "pct_repetidos"] if nome == "comentarios" else ["n_publicacoes", "n_perfis", "pct_perfil_top"]
        out = d[ordem[:-1] + extra + ["amostra_docs"]].copy()
        out.insert(4, "confere (S/N)", "")
        out.insert(5, "nota corrigida", "")
        out.insert(6, "motivo", "")
        out.round(3).to_excel(xw, sheet_name=nome, index=False)
dc.to_csv(M / "consolidado_comentarios.csv", index=False, encoding="utf-8")
dl.to_csv(M / "consolidado_legendas.csv", index=False, encoding="utf-8")
print("\nplanilha:", A / "conferencia_topicos.xlsx")
