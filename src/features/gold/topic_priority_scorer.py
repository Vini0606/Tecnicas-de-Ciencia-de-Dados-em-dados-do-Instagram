"""
Score ICE de priorização de tópicos de comentário (ADR 0020, Ficha 6 / issue
#91): `topic_priority_score`.

Estágio pós-modelagem, mesma posição/dependência da NSM (Ficha 5) --
`TopicPriorityScorer` lê só `governor_sentiment` (sentimento e tópico de
COMENTÁRIO, já produzidos por `run_deterministic_modeling`/BERTopic, ADR
0019), 100% automatizado, sem nenhum input humano do assessor. Não depende
de discurso oficial (`governor_discourse_topics`, Ficha 4) -- as duas fontes
respondem perguntas diferentes ("o que priorizar produzir" vs. "o que a
assessoria já falou").

Fórmula (fixa pela ADR 0020, não reaberta aqui):

    Score = Impacto x Confiança x Facilidade

- **Impacto** = alcance_normalizado(tópico) x proporção_sentimento_positivo(tópico)
- **Confiança** = média de `sentiment_score` (confiança do classificador na
  label prevista, NÃO "o quão positivo" -- ver `src/modeling/sentiment.py`)
  dentro do tópico
- **Facilidade** = fixa em `FACILIDADE_V1` (ver docstring da constante)

**Alcance do tópico -- heurística explícita, não literal**: `governor_sentiment`
não guarda alcance/views por comentário -- isso vive em `governor_engagement`,
por PERFIL, não por tópico (mesma lacuna de dado enfrentada pela NSM, Ficha
5). Juntar por `id_reel` a reels/engagement traria alcance real, mas
acoplaria este módulo a uma segunda tabela só para essa componente -- em vez
disso, "alcance do tópico" é aproximado pela soma do próprio engajamento do
comentário (`likesCount + repliesCount`) dentro do tópico: um proxy de
visibilidade/ressonância do tema, não impressões/views. Mantém o módulo
dependente só de `governor_sentiment` (mesmo raciocínio de escopo enxuto da
Ficha 5) e documentado como limitação, não escondido atrás do nome "alcance".

Normalização do alcance escolhida: `x / (x + 1)` -- satura suavemente em
[0, 1), nunca divide por zero (`x >= 0` sempre, por construção), e não faz o
score de um tópico depender de quais OUTROS tópicos aparecem na mesma
execução (ao contrário de um min-max entre tópicos do run, que tornaria o
ranking instável entre execuções com conjuntos de tópicos diferentes).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.delta_io import write_delta
from src.schemas_delta import GOLD_TOPIC_PRIORITY_SCORE_SCHEMA

_RESULT_COLUMNS = [
    "Topic",
    "Name",
    "n_comentarios",
    "alcance_topico",
    "alcance_normalizado",
    "proporcao_sentimento_positivo",
    "confianca",
    "impacto",
    "facilidade",
    "score",
]


class TopicPriorityScorer:
    # Facilidade v1: fixa em 1.0 -- decisão explícita da ADR 0020 (Ficha 6),
    # resolvida por esta issue entre as duas opções que a ADR deixou em
    # aberto ("heurística ou fixa em 1"). `governor_sentiment` não guarda
    # nenhum dado de custo/complexidade de produção por tópico (formato,
    # tempo de produção, etc.) -- qualquer heurística aqui (ex.: "tópicos
    # com Name mais curto são mais fáceis de produzir") seria um número
    # inventado sem lastro em dado real, o que a issue #91 pede
    # explicitamente para não fazer. Fixar em 1.0 documenta essa limitação
    # às claras (Facilidade não discrimina tópicos nesta v1 -- o ranking
    # de Score reduz-se a Impacto x Confiança) em vez de escondê-la atrás
    # de uma fórmula que pareceria fundamentada sem ser. Uma Facilidade
    # real (ex.: inverso de um custo de produção por formato de conteúdo)
    # fica para uma revisão futura, quando existir dado de custo real para
    # calibrar -- ver ADR 0020, "Opções consideradas".
    FACILIDADE_V1 = 1.0

    def score(self, df_sentiment: pd.DataFrame) -> pd.DataFrame:
        """Calcula o Score ICE por tópico de comentário. Uma linha de
        entrada por comentário avaliado (`governor_sentiment`); uma linha de
        saída por tópico, ordenada por `score` decrescente (ranking pronto
        para consumo, não só o dado bruto)."""
        required = {"Topic", "Name", "sentiment_label", "sentiment_score"}
        missing = required - set(df_sentiment.columns)
        if missing:
            raise ValueError(
                f"df_sentiment não tem as colunas esperadas: {sorted(missing)}"
            )

        df = df_sentiment.copy()

        # Score ICE é só sobre tópicos de COMENTÁRIO -- `governor_sentiment`
        # também acumula linhas de "legenda"/"transcricao" (ADR 0020 Ficha 3
        # / issue #88), que nunca passam pelo BERTopic de comentário (Topic/
        # Name ficam nulos para essas fontes, ver `run_deterministic_modeling`).
        # Filtrar por `fonte` explicitamente documenta a intenção, em vez de
        # confiar só no dropna(Topic) abaixo; `fonte` é opcional aqui (dado
        # sintético de teste, ou uma tabela futura sem a coluna, não quebra).
        if "fonte" in df.columns:
            df = df[df["fonte"] == "comentario"]

        # Topic == -1 é o rótulo de ruído/outlier do BERTopic (documentos que
        # não se encaixam em nenhum cluster coerente) -- não é um "tema" que
        # faça sentido priorizar para produção de conteúdo (mesmo raciocínio
        # já aplicado a outliers de cluster, `-1` de DBSCAN, no dashboard).
        df = df.dropna(subset=["Topic"])
        df = df[df["Topic"] != -1]

        if df.empty:
            return pd.DataFrame(columns=_RESULT_COLUMNS)

        for col in ("likesCount", "repliesCount"):
            if col not in df.columns:
                df[col] = 0
        likes = pd.to_numeric(df["likesCount"], errors="coerce").fillna(0.0)
        replies = pd.to_numeric(df["repliesCount"], errors="coerce").fillna(0.0)
        alcance_comentario = likes + replies
        positivo = df["sentiment_label"].astype(str).str.lower() == "positive"

        grouped = (
            df.assign(_alcance_comentario=alcance_comentario, _positivo=positivo)
            .groupby(["Topic", "Name"], dropna=False)
            .agg(
                n_comentarios=("_positivo", "size"),
                alcance_topico=("_alcance_comentario", "sum"),
                proporcao_sentimento_positivo=("_positivo", "mean"),
                confianca=("sentiment_score", "mean"),
            )
            .reset_index()
        )

        grouped["Topic"] = grouped["Topic"].astype("int64")
        grouped["n_comentarios"] = grouped["n_comentarios"].astype("int64")
        grouped["alcance_topico"] = grouped["alcance_topico"].astype("int64")
        # `sentiment_score` nulo em alguma linha (ex.: comentário vazio, ver
        # `analyze_sentiment`) não pode propagar NaN pro tópico inteiro --
        # `.mean()` já ignora NaN por padrão; o fillna(0.0) cobre só o caso
        # degenerado de um tópico onde TODAS as linhas têm score nulo.
        grouped["confianca"] = pd.to_numeric(grouped["confianca"], errors="coerce").fillna(0.0)

        grouped["alcance_normalizado"] = grouped["alcance_topico"] / (
            grouped["alcance_topico"] + 1.0
        )
        grouped["impacto"] = (
            grouped["alcance_normalizado"] * grouped["proporcao_sentimento_positivo"]
        )
        grouped["facilidade"] = self.FACILIDADE_V1
        grouped["score"] = grouped["impacto"] * grouped["confianca"] * grouped["facilidade"]

        # Ordenação por score decrescente com desempate por Topic (estável e
        # determinístico) -- entrega o ranking já pronto, não só o dado bruto
        # (issue #91, user story 1: "lista rankeada de temas").
        return (
            grouped[_RESULT_COLUMNS]
            .sort_values(["score", "Topic"], ascending=[False, True])
            .reset_index(drop=True)
        )

    def write(
        self,
        df_scored: pd.DataFrame,
        path: Path | str,
        run_id: str,
        mode: str = "overwrite",
        generated_at: datetime | None = None,
    ) -> None:
        """Grava `topic_priority_score` -- uma linha por tópico, saída de
        `score()`. `generated_at` explícito opcional, mesmo padrão de
        `ModelEnricher.write_sentiment`, para carimbar o mesmo timestamp de
        outras tabelas escritas no mesmo `run_id`."""
        df = df_scored.copy()
        df["_run_id"] = run_id
        df["_generated_at"] = generated_at or datetime.now(timezone.utc)
        write_delta(path, df, GOLD_TOPIC_PRIORITY_SCORE_SCHEMA, mode=mode)
