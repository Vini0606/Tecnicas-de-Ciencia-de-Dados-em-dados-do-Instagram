"""Camadas 2 (validade convergente/externa, descritiva) e 3 (NPMI em variantes de protocolo) por topico.
Uso (venv Py3.12): python camadas_2_3.py <repo> <run_id> <pasta_saida>

Camada 3, variantes do NPMI (top-10 palavras finais, topico -1 fora, contagens no proprio corpus):
  doc        documento inteiro como janela, textos distintos (protocolo ja calculado)
  publicacao comentarios agregados por publicacao (pseudodocumento; so comentarios)
  janela10   janela deslizante de 10 tokens (protocolo de Lau et al., 2014, aqui sobre o proprio corpus)
  observados media so dos pares que coocorrem ao menos uma vez (sensibilidade a convencao do -1)
  suavizado  contagem de coocorrencia +1 (sensibilidade; o par nunca visto deixa de valer -1)
Linha de base: 300 topicos de 10 palavras sorteadas (df >= 5), semente 42, para cada variante.
"""
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from bertopic import BERTopic
from scipy import sparse

REPO, RUN, OUT = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
CK = REPO / "data" / "model_checkpoints" / RUN
OUT.mkdir(parents=True, exist_ok=True)
K, JANELA = 10, 10


def palavras_topicos(modelo):
    return {t: [w for i, (w, p) in enumerate(ws) if w and not (i == 0 and float(p) == 1.0)][:K]
            for t, ws in modelo.get_topics().items() if t != -1}


def matriz_binaria(unidades, vocab):
    """unidades: lista de listas de tokens -> matriz binaria (unidade x vocab), CSC."""
    linhas, cols = [], []
    for i, toks in enumerate(unidades):
        for j in {vocab[w] for w in toks if w in vocab}:
            linhas.append(i)
            cols.append(j)
    X = sparse.csr_matrix((np.ones(len(linhas), dtype=np.int32), (linhas, cols)), shape=(len(unidades), len(vocab)))
    return X.tocsc()


def npmi_pares(palavras, X, vocab, n, modo="padrao"):
    idx = [vocab[w] for w in palavras if w in vocab]
    sub = X[:, idx]
    co = (sub.T @ sub).toarray()
    df = co.diagonal().astype(float)
    vals, zeros = [], 0
    for a, b in itertools.combinations(range(len(idx)), 2):
        c = co[a, b]
        if modo == "suavizado":
            c = c + 1
        if c == 0:
            zeros += 1
            if modo == "observados":
                continue
            vals.append(-1.0)
            continue
        pij = c / n
        if pij >= 1.0:
            vals.append(1.0)
            continue
        vals.append(math.log(pij / ((df[a] / n) * (df[b] / n))) / -math.log(pij))
    return (float(np.mean(vals)) if vals else float("nan")), zeros


def janelas(tokens_docs):
    out = []
    for toks in tokens_docs:
        if len(toks) <= JANELA:
            out.append(toks)
        else:
            out.extend(toks[i:i + JANELA] for i in range(len(toks) - JANELA + 1))
    return out


def avaliar(nome, modelo, unidades_por_variante):
    topicos = palavras_topicos(modelo)
    vocab_top = sorted({w for ws in topicos.values() for w in ws})
    linhas = {t: {"modelo": nome, "topico": int(t), "palavras": " ".join(ws)} for t, ws in topicos.items()}
    resumo = {"modelo": nome}
    for variante, unidades in unidades_por_variante.items():
        # vocabulario: palavras dos topicos + candidatas para a linha de base (df >= 5 em unidades distintas)
        cont = {}
        for toks in unidades:
            for w in set(toks):
                cont[w] = cont.get(w, 0) + 1
        cand = sorted(w for w, c in cont.items() if c >= 5)
        vocab = {w: i for i, w in enumerate(sorted(set(vocab_top) | set(cand)))}
        X = matriz_binaria(unidades, vocab)
        n = len(unidades)
        modos = ["padrao"] if variante != "doc" else ["padrao", "observados", "suavizado"]
        for modo in modos:
            col = variante if modo == "padrao" else modo
            for t, ws in topicos.items():
                v, z = npmi_pares(ws, X, vocab, n, modo)
                linhas[t][f"npmi_{col}"] = v
                if modo == "padrao":
                    linhas[t][f"zeros_{col}"] = z
            rng = np.random.default_rng(42)
            base = [npmi_pares(list(rng.choice(cand, K, replace=False)), X, vocab, n, modo)[0] for _ in range(300)]
            vals = [linhas[t][f"npmi_{col}"] for t in topicos]
            resumo[col] = {"n_unidades": n, "media": float(np.nanmean(vals)), "mediana": float(np.nanmedian(vals)),
                           "positivos": int(np.sum(np.array(vals) > 0)), "aleatorio": float(np.nanmean(base)),
                           "aleatorio_p95": float(np.nanpercentile(base, 95))}
            print(f"  {nome:12s} {col:11s} n={n:>7} media={resumo[col]['media']:+.3f} mediana={resumo[col]['mediana']:+.3f}"
                  f" positivos={resumo[col]['positivos']:>3}/{len(topicos)} aleatorio={resumo[col]['aleatorio']:+.3f}"
                  f" (p95 {resumo[col]['aleatorio_p95']:+.3f})")
    return pd.DataFrame(linhas.values()), resumo


com = pd.read_parquet(CK / "df_comments.parquet")
disc = pd.read_parquet(CK / "df_discourse.parquet")
m_com = BERTopic.load(str(CK / "topic_model"))
m_disc = BERTopic.load(str(CK / "discourse_topic_model"))

# ---------- camada 3 ----------
an_com, an_disc = m_com.vectorizer_model.build_analyzer(), m_disc.vectorizer_model.build_analyzer()
docs_com = sorted(set(com["text_demojized"].fillna("").astype(str)))
tok_com = [an_com(d) for d in docs_com]
por_post = com.assign(_t=com["text_demojized"].fillna("").astype(str)).groupby("id_reel")["_t"].apply(" ".join)
tok_post = [an_com(d) for d in por_post]
docs_disc = sorted(set(disc["text"].fillna("").astype(str)))
tok_disc = [an_disc(d) for d in docs_disc]
print("comprimento mediano (tokens): comentarios", np.median([len(t) for t in tok_com]),
      "| publicacao (comentarios agregados)", np.median([len(t) for t in tok_post]),
      "| legendas", np.median([len(t) for t in tok_disc]))
print("camada 3")
t3_com, r3_com = avaliar("comentarios", m_com, {"doc": tok_com, "publicacao": tok_post, "janela10": janelas(tok_com)})
t3_disc, r3_disc = avaliar("legendas", m_disc, {"doc": tok_disc, "janela10": janelas(tok_disc)})

# ---------- camada 2 ----------
com["perfil"] = com["inputUrl"].str.extract(r"instagram\.com/([^/?]+)")[0]
com["semana"] = pd.to_datetime(com["timestamp"], utc=True, errors="coerce").dt.to_period("W").astype(str)
g = com[com.Topic != -1].groupby("Topic")
t2_com = pd.DataFrame({
    "n_comentarios": g.size(),
    "n_textos_distintos": g["text"].nunique(),
    "n_autores": g["ownerUsername"].nunique(),
    "n_perfis": g["perfil"].nunique(),
    "pct_perfil_top": g["perfil"].agg(lambda s: s.value_counts(normalize=True).iloc[0] * 100),
    "perfil_top": g["perfil"].agg(lambda s: s.value_counts().index[0]),
    "pct_semana_top": g["semana"].agg(lambda s: s.value_counts(normalize=True).iloc[0] * 100),
    "pct_pos": g["sentiment_label"].agg(lambda s: (s == "positive").mean() * 100),
    "pct_neg": g["sentiment_label"].agg(lambda s: (s == "negative").mean() * 100),
}).reset_index().rename(columns={"Topic": "topico"})
t2_com["pct_repetidos"] = (1 - t2_com.n_textos_distintos / t2_com.n_comentarios) * 100
t2_com["comentarios_por_autor"] = t2_com.n_comentarios / t2_com.n_autores

disc["semana"] = pd.to_datetime(disc["timestamp"], errors="coerce").dt.to_period("W").astype(str)
g = disc[disc.Topic != -1].groupby("Topic")
t2_disc = pd.DataFrame({
    "n_publicacoes": g.size(),
    "n_perfis": g["ownerUsername"].nunique(),
    "pct_perfil_top": g["ownerUsername"].agg(lambda s: s.value_counts(normalize=True).iloc[0] * 100),
    "perfil_top": g["ownerUsername"].agg(lambda s: s.value_counts().index[0]),
    "pct_semana_top": g["semana"].agg(lambda s: s.value_counts(normalize=True).iloc[0] * 100),
    "curtidas_mediana": g["likesCount"].median(),
}).reset_index().rename(columns={"Topic": "topico"})

com_final = t3_com.merge(t2_com, on="topico")
disc_final = t3_disc.merge(t2_disc, on="topico")
com_final.to_csv(OUT / "metricas_comentarios.csv", index=False, encoding="utf-8")
disc_final.to_csv(OUT / "metricas_legendas.csv", index=False, encoding="utf-8")
(OUT / "resumo_camada3.json").write_text(json.dumps([r3_com, r3_disc], ensure_ascii=False, indent=1), encoding="utf-8")

print("\ncamada 2, comentarios: perfis por topico (mediana)", com_final.n_perfis.median(),
      "| topicos com >=80% num perfil:", int((com_final.pct_perfil_top >= 80).sum()),
      "| topicos com >=50% numa semana:", int((com_final.pct_semana_top >= 50).sum()),
      "| topicos com >=50% de textos repetidos:", int((com_final.pct_repetidos >= 50).sum()))
print("camada 2, legendas: perfis por pauta (mediana)", disc_final.n_perfis.median(),
      "| pautas de um so perfil:", int((disc_final.n_perfis == 1).sum()),
      "| pautas com >=50% numa semana:", int((disc_final.pct_semana_top >= 50).sum()))
