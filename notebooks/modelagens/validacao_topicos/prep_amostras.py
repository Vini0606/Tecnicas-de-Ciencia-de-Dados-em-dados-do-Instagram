"""Camada 1: amostras cegas por topico para a anotacao qualitativa.
Uso (venv Py3.12): python prep_amostras.py <repo> <run_id> <pasta_saida>

Por topico (exceto -1): as 10 palavras-chave finais (as do modelo refinado, sem o rotulo do LLM),
3 documentos representativos do BERTopic + 12 sorteados (semente 42) entre os textos distintos do
topico, no texto original (sem remocao de stopwords). Legendas cortadas em 450 caracteres.
Saida cega: lote_<modelo>_<n>.json (sem tamanho, sentimento, perfil, NPMI nem rotulo Gemini);
rotulos_<modelo>_<n>.json guarda o rotulo Gemini, aberto pelo anotador so depois de anotar o lote.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from bertopic import BERTopic

REPO, RUN, OUT = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
CK = REPO / "data" / "model_checkpoints" / RUN
OUT.mkdir(parents=True, exist_ok=True)
N_REP, N_SORT, CORTE = 3, 12, 450


def palavras_e_rotulo(ws):
    rotulo = ws[0][0] if ws and float(ws[0][1]) == 1.0 else None
    palavras = [w for i, (w, p) in enumerate(ws) if w and not (i == 0 and float(p) == 1.0)][:10]
    return palavras, rotulo


def montar(nome, modelo, df, lotes):
    rng = np.random.default_rng(42)
    topicos = []
    for t, ws in sorted(modelo.get_topics().items()):
        if t == -1:
            continue
        palavras, rotulo = palavras_e_rotulo(ws)
        sub = df[df.Topic == t]
        textos = pd.Series(sub["text"].fillna("").astype(str).str.strip().unique())
        textos = textos[textos != ""]
        rep = sub["Representative_Docs"].iloc[0] if len(sub) else []
        # representativos do BERTopic vem no texto pre-processado; troca pelo original quando possivel
        rep_orig = []
        for r in list(rep)[:N_REP]:
            m = sub.loc[sub.get("text_demojized", sub["text"]).astype(str) == str(r), "text"]
            rep_orig.append(str(m.iloc[0]) if len(m) else str(r))
        resto = textos[~textos.isin(rep_orig)]
        k = min(N_SORT, len(resto))
        sorteio = list(resto.iloc[rng.choice(len(resto), k, replace=False)]) if k else []
        docs = [d if len(d) <= CORTE else d[:CORTE] + " [...]" for d in rep_orig + sorteio]
        topicos.append({"topico": int(t), "palavras": palavras, "documentos": docs, "_rotulo": rotulo})
    partes = np.array_split(np.arange(len(topicos)), lotes)
    for i, idx in enumerate(partes, 1):
        lote = [topicos[j] for j in idx]
        cego = [{k: v for k, v in t.items() if k != "_rotulo"} for t in lote]
        (OUT / f"lote_{nome}_{i}.json").write_text(json.dumps(cego, ensure_ascii=False, indent=1), encoding="utf-8")
        (OUT / f"rotulos_{nome}_{i}.json").write_text(
            json.dumps({str(t["topico"]): t["_rotulo"] for t in lote}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(nome, i, len(lote), "topicos", f"{lote[0]['topico']}..{lote[-1]['topico']}",
              round((OUT / f"lote_{nome}_{i}.json").stat().st_size / 1024), "KB")


com = pd.read_parquet(CK / "df_comments.parquet")
disc = pd.read_parquet(CK / "df_discourse.parquet")
montar("comentarios", BERTopic.load(str(CK / "topic_model")), com, 2)
montar("legendas", BERTopic.load(str(CK / "discourse_topic_model")), disc, 6)
