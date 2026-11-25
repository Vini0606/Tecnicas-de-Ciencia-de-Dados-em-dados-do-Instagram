"""Coerencia (NPMI) e diversidade dos dois modelos BERTopic do checkpoint.
Uso (venv Py3.12): python npmi_diversidade.py <repo> <run_id> <saida.json>

NPMI: coocorrencia em documento (o documento inteiro e a janela), contagens no proprio corpus
modelado, 10 palavras principais por topico (45 pares), par que nunca coocorre = -1
(Lau et al., 2014; protocolo de Dieng et al., 2020). Diversidade: fracao de palavras unicas
entre as 10 principais de todos os topicos (Dieng et al., 2020, com k=10). Topico -1 fora."""
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from bertopic import BERTopic
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer

REPO, RUN, SAIDA = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
CK = REPO / "data" / "model_checkpoints" / RUN
K = 10


def npmi_topico(palavras, X, vocab, n_docs):
    idx = [vocab[w] for w in palavras if w in vocab]
    fora = [w for w in palavras if w not in vocab]
    sub = (X[:, idx] > 0).astype(np.int32)
    co = (sub.T @ sub).toarray()
    df = co.diagonal()
    vals = []
    for a, b in itertools.combinations(range(len(idx)), 2):
        if co[a, b] == 0:
            vals.append(-1.0)
            continue
        pij = co[a, b] / n_docs
        if pij >= 1.0:
            vals.append(1.0)
            continue
        vals.append(math.log(pij / ((df[a] / n_docs) * (df[b] / n_docs))) / -math.log(pij))
    return (float(np.mean(vals)) if vals else float("nan")), fora, int(sum(v == -1.0 for v in vals)), len(vals)


def avaliar(nome, modelo, docs):
    analisador = modelo.vectorizer_model.build_analyzer()
    # O refinamento por LLM grava o rotulo como primeiro item (peso 1.0); as palavras do corpus
    # (ordem do c-TF-IDF) vem depois. O rotulo sai da avaliacao.
    completos = {t: [w for i, (w, peso) in enumerate(ws) if w and not (i == 0 and float(peso) == 1.0)]
                 for t, ws in modelo.get_topics().items() if t != -1}
    topicos = {t: ws[:K] for t, ws in completos.items()}
    res = {"modelo": nome, "n_topicos": len(topicos), "k": K}
    unicos = sorted(set(docs))
    for base_nome, base in (("unicos", unicos), ("todos", docs)):
        cv = CountVectorizer(analyzer=analisador)
        X = sparse.csc_matrix(cv.fit_transform(base))
        vocab, n = cv.vocabulary_, len(base)
        linhas = []
        for t, ws in topicos.items():
            v, fora, n_zero, n_pares = npmi_topico(ws, X, vocab, n)
            linhas.append({"topico": int(t), "npmi": v, "n_palavras": len(ws), "fora_vocab": fora, "pares_sem_coocorrencia": n_zero, "pares": n_pares, "palavras": ws})
        d = pd.DataFrame(linhas)
        # referencia: topicos de 10 palavras sorteadas do vocabulario (df >= 5)
        df_vocab = np.asarray((X > 0).sum(axis=0)).ravel()
        inv = {i: w for w, i in vocab.items()}
        cand = [inv[i] for i in np.where(df_vocab >= 5)[0]]
        rng = np.random.default_rng(42)
        aleat = [npmi_topico(list(rng.choice(cand, K, replace=False)), X, vocab, n)[0] for _ in range(300)]
        res[base_nome] = {
            "n_docs": n, "vocab": len(vocab), "npmi_media": float(d.npmi.mean()), "npmi_mediana": float(d.npmi.median()),
            "npmi_min": float(d.npmi.min()), "npmi_max": float(d.npmi.max()), "npmi_positivos": int((d.npmi > 0).sum()),
            "pares_sem_coocorrencia_pct": float(d.pares_sem_coocorrencia.sum() / d.pares.sum() * 100),
            "npmi_aleatorio_media": float(np.mean(aleat)), "topicos": linhas,
        }
    todas = [w for ws in topicos.values() for w in ws]
    res["diversidade"] = len(set(todas)) / len(todas)
    res["n_palavras_total"], res["n_palavras_unicas"] = len(todas), len(set(todas))
    t25 = [w for ws in completos.values() for w in ws[:25]]
    res["diversidade_top25"] = len(set(t25)) / len(t25)
    res["palavras_por_topico_disponiveis"] = [min(len(ws) for ws in completos.values()), max(len(ws) for ws in completos.values())]
    rep = pd.Series(todas).value_counts()
    res["palavras_mais_repetidas"] = rep[rep > 1].head(15).to_dict()
    tam = modelo.get_topic_info().set_index("Topic").Count
    res["ruido_docs_unicos"] = int(tam.get(-1, 0))
    res["docs_no_ajuste"] = int(tam.sum())
    return res


com = pd.read_parquet(CK / "df_comments.parquet")
disc = pd.read_parquet(CK / "df_discourse.parquet")
saida = []
for nome, pasta, docs in (("comentarios", "topic_model", com["text_demojized"].fillna("").tolist()),
                          ("legendas", "discourse_topic_model", disc["text"].fillna("").tolist())):
    m = BERTopic.load(str(CK / pasta))
    r = avaliar(nome, m, docs)
    saida.append(r)
    print(f"\n## {nome}: {r['n_topicos']} topicos | diversidade top-{K}: {r['diversidade']:.3f} ({r['n_palavras_unicas']}/{r['n_palavras_total']})")
    print("diversidade top-25:", round(r["diversidade_top25"], 3), "| palavras disponiveis por topico (min, max):", r["palavras_por_topico_disponiveis"])
    print("ajuste:", r["docs_no_ajuste"], "docs unicos | ruido:", r["ruido_docs_unicos"])
    for b in ("unicos", "todos"):
        x = r[b]
        print(f"  [{b}] n={x['n_docs']} vocab={x['vocab']} NPMI media={x['npmi_media']:.3f} mediana={x['npmi_mediana']:.3f} min={x['npmi_min']:.3f} max={x['npmi_max']:.3f} positivos={x['npmi_positivos']}/{r['n_topicos']} pares sem cooc={x['pares_sem_coocorrencia_pct']:.1f}% | aleatorio={x['npmi_aleatorio_media']:.3f}")
    print("  repetidas:", r["palavras_mais_repetidas"])
    d = pd.DataFrame(r["unicos"]["topicos"]).sort_values("npmi")
    d["palavras"] = d.palavras.map(lambda ws: " ".join(ws)[:110])
    pd.set_option("display.width", 220, "display.max_colwidth", 115, "display.max_rows", 400)
    print("  piores:\n", d.head(6)[["topico", "npmi", "pares_sem_coocorrencia", "palavras"]].to_string(index=False))
    print("  melhores:\n", d.tail(6)[["topico", "npmi", "pares_sem_coocorrencia", "palavras"]].to_string(index=False))
    print("  fora do vocabulario:", sum(len(t["fora_vocab"]) for t in r["unicos"]["topicos"]), "| topicos com <10 palavras:", int((d.n_palavras < K).sum()))
SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
