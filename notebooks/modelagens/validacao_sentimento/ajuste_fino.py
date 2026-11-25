"""Ajuste fino do classificador de sentimentos nos comentários anotados
(`sentimento_02_comparacao_de_metodos.ipynb`).

Parte do `cardiffnlp/twitter-xlm-roberta-base-sentiment` e continua o treino nos
textos de `treino_para_rotular.csv` com os rótulos de `treino_rotulos_anotador.csv`.

Cuidados contra vazamento:

- este script **nunca lê os rótulos do teste** (`teste_rotulos_anotador.csv`);
- a época e a taxa de aprendizado são escolhidas no conjunto de
  **desenvolvimento** (a amostra da primeira validação), não no teste;
- as previsões no teste são geradas uma única vez, com a configuração já
  escolhida;
- antes de treinar, confere que nenhum texto normalizado do treino aparece no
  teste ou no desenvolvimento e que nenhuma publicação do treino tem comentário
  no teste.

Uso (a partir da raiz do repositório):

    python notebooks/modelagens/validacao_sentimento/ajuste_fino.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

PASTA = Path(__file__).resolve().parent
RAIZ = PASTA.parents[2]
sys.path.insert(0, str(PASTA))
sys.path.insert(0, str(RAIZ))

import amostragem as am
import particao

MODELO_BASE = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
SEMENTE = am.SEED
MAX_TOKENS = 64
LOTE = 16
EPOCAS = 4
TAXAS = (1e-5, 3e-5)
AQUECIMENTO = 0.1

ARQ_PREVISOES_TESTE = PASTA / "ajuste_fino_previsoes_teste.csv"
ARQ_PREVISOES_DEV = PASTA / "ajuste_fino_previsoes_dev.csv"
ARQ_LOG = PASTA / "ajuste_fino_log.json"
PASTA_MODELO = RAIZ / "data" / "model_checkpoints" / "sentimento_ajuste_fino"


def carregar_treino() -> pd.DataFrame:
    textos = pd.read_csv(particao.ARQ_TREINO)
    rotulos = pd.read_csv(PASTA / "treino_rotulos_anotador.csv")
    treino = textos.merge(rotulos, on="id_amostra", validate="one_to_one")
    assert len(treino) == len(textos) and set(treino["rotulo"]) <= set(am.CLASSES)
    return treino


def carregar_dev() -> pd.DataFrame:
    """Amostra da primeira validação, com o rótulo conferido quando houver."""
    planilha = pd.read_excel(PASTA / "planilha_conferencia.xlsx", dtype=str, keep_default_na=False)
    revisado = planilha["rotulo_revisado"].str.strip().str.lower()
    planilha["rotulo"] = np.where(revisado != "", revisado, planilha["rotulo_anotador"])
    gabarito = pd.read_csv(am.ARQ_GABARITO)[["id_amostra", "estrato", "sentiment_label"]]
    return planilha[["id_amostra", "text", "rotulo"]].merge(gabarito, on="id_amostra")


def conferir_vazamento(treino: pd.DataFrame, dev: pd.DataFrame, teste: pd.DataFrame) -> dict:
    chaves_treino = set(treino["text"].map(particao.chave_texto))
    chaves_teste = set(teste["text"].map(particao.chave_texto))
    chaves_dev = set(dev["text"].map(particao.chave_texto))
    publicacoes_teste = set(pd.read_csv(particao.ARQ_TESTE_GABARITO)["id_reel"].astype(str))
    conferencia = {
        "textos_do_treino_no_teste": len(chaves_treino & chaves_teste),
        "textos_do_treino_no_desenvolvimento": len(chaves_treino & chaves_dev),
        "publicacoes_do_treino_no_teste": len(set(treino["id_reel"].astype(str)) & publicacoes_teste),
        "comentarios_do_teste_no_desenvolvimento": len(
            set(pd.read_csv(particao.ARQ_TESTE_GABARITO)["id_comment"].astype(str))
            & particao.ids_da_primeira_validacao()
        ),
    }
    assert not any(conferencia.values()), f"vazamento entre conjuntos: {conferencia}"
    return conferencia


def f1_macro_ponderado(dev: pd.DataFrame, previsto: np.ndarray, pesos: np.ndarray) -> float:
    """F1-macro estimado para a população: a amostra de desenvolvimento é
    estratificada pela classe do classificador original, e cada estrato entra
    com o seu peso na população."""
    principal = dev["estrato"].to_numpy() == "principal"
    J = np.zeros((3, 3))
    for i, classe in enumerate(am.CLASSES):
        estrato = principal & (dev["sentiment_label"].to_numpy() == classe)
        for a, prev in enumerate(am.CLASSES):
            for b, real in enumerate(am.CLASSES):
                J[a, b] += pesos[i] * np.sum((previsto[estrato] == prev) & (dev["rotulo"].to_numpy()[estrato] == real)) / estrato.sum()
    with np.errstate(invalid="ignore", divide="ignore"):
        precisao = np.diag(J) / J.sum(axis=1)
        revocacao = np.diag(J) / J.sum(axis=0)
        f1 = np.nan_to_num(2 * precisao * revocacao / (precisao + revocacao))
    return float(f1.mean())


def prever(modelo, tokenizador, textos: list[str]) -> np.ndarray:
    modelo.eval()
    saidas = []
    with torch.no_grad():
        for i in range(0, len(textos), 64):
            lote = tokenizador(textos[i : i + 64], truncation=True, max_length=MAX_TOKENS, padding=True, return_tensors="pt")
            saidas.append(torch.softmax(modelo(**lote).logits, dim=-1).numpy())
    return np.concatenate(saidas)


def treinar(treino, dev, pesos_populacao, taxa, tokenizador, id_de_classe):
    torch.manual_seed(SEMENTE)
    modelo = AutoModelForSequenceClassification.from_pretrained(MODELO_BASE)
    classes_do_modelo = [modelo.config.id2label[i].lower() for i in range(3)]

    textos = treino["text"].astype(str).tolist()
    alvos = torch.tensor([id_de_classe[r] for r in treino["rotulo"]])
    # Perda ponderada pelo inverso da raiz da frequência: a classe menos
    # frequente no treino pesa mais, sem dominar.
    freq = np.bincount(alvos.numpy(), minlength=3) / len(alvos)
    perda = torch.nn.CrossEntropyLoss(weight=torch.tensor((1 / np.sqrt(freq)) / (1 / np.sqrt(freq)).mean(), dtype=torch.float))

    otimizador = torch.optim.AdamW(modelo.parameters(), lr=taxa, weight_decay=0.01)
    passos = EPOCAS * int(np.ceil(len(textos) / LOTE))
    agenda = torch.optim.lr_scheduler.LambdaLR(
        otimizador,
        lambda p: min((p + 1) / (AQUECIMENTO * passos), max(0.0, (passos - p) / ((1 - AQUECIMENTO) * passos))),
    )
    gerador = np.random.default_rng(SEMENTE)
    historico, melhor = [], {"f1_dev": -1.0}
    for epoca in range(1, EPOCAS + 1):
        modelo.train()
        ordem, perdas = gerador.permutation(len(textos)), []
        for i in range(0, len(ordem), LOTE):
            idx = ordem[i : i + LOTE]
            lote = tokenizador([textos[j] for j in idx], truncation=True, max_length=MAX_TOKENS, padding=True, return_tensors="pt")
            valor = perda(modelo(**lote).logits, alvos[idx])
            valor.backward()
            torch.nn.utils.clip_grad_norm_(modelo.parameters(), 1.0)
            otimizador.step()
            agenda.step()
            otimizador.zero_grad()
            perdas.append(float(valor))
        prob_dev = prever(modelo, tokenizador, dev["text"].astype(str).tolist())
        prev_dev = np.array(classes_do_modelo)[prob_dev.argmax(axis=1)]
        f1_dev = f1_macro_ponderado(dev, prev_dev, pesos_populacao)
        historico.append({"taxa": taxa, "epoca": epoca, "perda_treino": float(np.mean(perdas)), "f1_macro_dev": f1_dev})
        print(f"  taxa {taxa:g} época {epoca}: perda {np.mean(perdas):.4f}  F1-macro dev {f1_dev:.4f}", flush=True)
        if f1_dev > melhor["f1_dev"]:
            melhor = {"f1_dev": f1_dev, "epoca": epoca, "taxa": taxa,
                      "estado": {k: v.clone() for k, v in modelo.state_dict().items()}, "prev_dev": prev_dev}
    return historico, melhor, classes_do_modelo


def main() -> None:
    from src.repositories.delta_repository import DeltaRepository

    inicio = time.time()
    torch.set_num_threads(torch.get_num_threads())
    treino, dev = carregar_treino(), carregar_dev()
    teste = pd.read_csv(particao.ARQ_TESTE)  # só id e texto: os rótulos do teste não são lidos aqui
    conferencia = conferir_vazamento(treino, dev, teste)

    repo = DeltaRepository(RAIZ / "data" / "gold", RAIZ / "data" / "silver", RAIZ / "data" / "bronze")
    pesos = am.carregar_populacao(repo)["sentiment_label"].value_counts(normalize=True).reindex(am.CLASSES).to_numpy()

    tokenizador = AutoTokenizer.from_pretrained(MODELO_BASE)
    base = AutoModelForSequenceClassification.from_pretrained(MODELO_BASE)
    id_de_classe = {base.config.id2label[i].lower(): i for i in range(3)}
    classes_base = [base.config.id2label[i].lower() for i in range(3)]
    prev_dev_base = np.array(classes_base)[prever(base, tokenizador, dev["text"].astype(str).tolist()).argmax(axis=1)]
    f1_dev_base = f1_macro_ponderado(dev, prev_dev_base, pesos)
    print(f"Modelo original no desenvolvimento: F1-macro {f1_dev_base:.4f}", flush=True)
    del base

    historico, melhor = [], {"f1_dev": -1.0}
    for taxa in TAXAS:
        hist, candidato, classes_do_modelo = treinar(treino, dev, pesos, taxa, tokenizador, id_de_classe)
        historico += hist
        if candidato["f1_dev"] > melhor["f1_dev"]:
            melhor = candidato

    modelo = AutoModelForSequenceClassification.from_pretrained(MODELO_BASE)
    modelo.load_state_dict(melhor["estado"])
    PASTA_MODELO.mkdir(parents=True, exist_ok=True)
    modelo.save_pretrained(PASTA_MODELO)
    tokenizador.save_pretrained(PASTA_MODELO)

    prob_teste = prever(modelo, tokenizador, teste["text"].astype(str).tolist())
    saida = pd.DataFrame(prob_teste, columns=[f"prob_{c}" for c in classes_do_modelo])
    saida.insert(0, "previsto_ajuste_fino", np.array(classes_do_modelo)[prob_teste.argmax(axis=1)])
    saida.insert(0, "id_amostra", teste["id_amostra"])
    saida.to_csv(ARQ_PREVISOES_TESTE, index=False)
    pd.DataFrame({"id_amostra": dev["id_amostra"], "previsto_ajuste_fino": melhor["prev_dev"]}).to_csv(ARQ_PREVISOES_DEV, index=False)

    ARQ_LOG.write_text(json.dumps({
        "modelo_base": MODELO_BASE,
        "semente": SEMENTE,
        "max_tokens": MAX_TOKENS,
        "lote": LOTE,
        "epocas": EPOCAS,
        "taxas_testadas": list(TAXAS),
        "n_treino": len(treino),
        "distribuicao_treino": treino["rotulo"].value_counts().to_dict(),
        "n_desenvolvimento": len(dev),
        "n_teste": len(teste),
        "conferencia_de_vazamento": conferencia,
        "f1_macro_dev_modelo_original": f1_dev_base,
        "historico": historico,
        "escolhido": {"taxa": melhor["taxa"], "epoca": melhor["epoca"], "f1_macro_dev": melhor["f1_dev"]},
        "minutos": round((time.time() - inicio) / 60, 1),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escolhido: taxa {melhor['taxa']:g}, época {melhor['epoca']}, F1-macro dev {melhor['f1_dev']:.4f}")


if __name__ == "__main__":
    main()
