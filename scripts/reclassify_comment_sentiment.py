"""
Reclassifica o sentimento dos comentarios ja gravados na Gold com o
classificador ajustado ao dominio (ADR 0049) e recalcula so as tabelas que
dependem desse rotulo:

- `governor_sentiment` e `governor_sentiment_history` (`sentiment_label` e
  `sentiment_score` do modelo ajustado; `sentiment_label_modelo` guarda o
  rotulo do classificador pre-treinado, para auditoria);
- `topic_priority_score` e `content_topic_priority_score` (Score ICE);
- `governor_nsm`;
- `governor_scorecard`;
- `governor_growth_metrics`.

Nao reexecuta o BERTopic: os topicos (`Topic`/`Name`, ja refinados) sao
preservados. Legenda e transcricao nao sao tocadas (seguem no pre-treinado).

As previsoes por texto ficam em cache (`--cache`), entao uma execucao
interrompida ou um `--dry-run` nao repetem a inferencia.

Leitura sempre via `DeltaRepository`; escrita pelos writers de cada tabela.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

import pandas as pd

from config import settings
from src.delta_io import write_delta
from src.features.gold.content_topic_priority_scorer import ContentTopicPriorityScorer
from src.features.gold.model_enricher import ModelEnricher
from src.features.gold.nsm_scorer import NsmScorer
from src.features.gold.topic_priority_scorer import TopicPriorityScorer
from src.modeling.config import ModelingConfig
from src.modeling.governor_scorecard import GovernorScorecardScorer
from src.modeling.growth_history import compute_growth_metrics
from src.modeling.sentiment import analyze_sentiment
from src.modeling.sentiment_rules import COLUNA_ROTULO_MODELO
from src.repositories.delta_repository import DeltaRepository
from src.run_id import build_run_id
from src.schemas_delta import GOLD_SENTIMENT_SCHEMA

CACHE_PADRAO = settings.MODEL_CHECKPOINTS_DIR / "sentimento_ajuste_fino_previsoes.parquet"
TAMANHO_DO_BLOCO = 2000


def _prever_por_texto(textos: pd.Series, cache: Path) -> pd.DataFrame:
    """Rotulo e confianca do modelo ajustado para cada texto distinto, indexado
    pelo texto. So classifica o que ainda nao esta no cache."""
    distintos = pd.unique(textos.dropna())
    previsoes = (
        pd.read_parquet(cache)
        if cache.exists()
        else pd.DataFrame(columns=["text", "sentiment_label", "sentiment_score"])
    )
    ja_previstos = set(previsoes["text"])
    faltam = pd.DataFrame({"text": [t for t in distintos if t not in ja_previstos]})
    if not faltam.empty:
        from src.modeling.sentiment import _build_pipeline

        config = ModelingConfig().comment_sentiment
        analisador = _build_pipeline(config.model_name)
        cache.parent.mkdir(parents=True, exist_ok=True)
        print(f"[SENTIMENTO] Classificando {len(faltam)} textos distintos...", flush=True)
        # Em blocos, gravando o cache a cada um: uma interrupcao perde no
        # maximo um bloco.
        for inicio in range(0, len(faltam), TAMANHO_DO_BLOCO):
            bloco = faltam.iloc[inicio : inicio + TAMANHO_DO_BLOCO]
            novas = analyze_sentiment(bloco, config, sentiment_pipeline=analisador)
            previsoes = pd.concat([previsoes, novas], ignore_index=True)
            previsoes.to_parquet(cache, index=False)
            print(f"  {min(inicio + TAMANHO_DO_BLOCO, len(faltam))}/{len(faltam)}", flush=True)
    return previsoes.drop_duplicates("text").set_index("text")


def _reclassificar_comentarios(df: pd.DataFrame, previsoes: pd.DataFrame) -> pd.DataFrame:
    """Troca rotulo e confianca das linhas `fonte == "comentario"` pelos do
    modelo ajustado. `sentiment_label_modelo` fica com o rotulo do classificador
    pre-treinado (o que ja estava guardado ou, em linhas antigas, o proprio
    `sentiment_label`). Idempotente."""
    df = df.copy()
    if COLUNA_ROTULO_MODELO not in df.columns:
        df[COLUNA_ROTULO_MODELO] = None
    eh_comentario = df["fonte"] == "comentario"
    df.loc[eh_comentario, COLUNA_ROTULO_MODELO] = df.loc[
        eh_comentario, COLUNA_ROTULO_MODELO
    ].fillna(df.loc[eh_comentario, "sentiment_label"])
    texto = df.loc[eh_comentario, "text"]
    df.loc[eh_comentario, "sentiment_label"] = texto.map(previsoes["sentiment_label"])
    df.loc[eh_comentario, "sentiment_score"] = texto.map(previsoes["sentiment_score"]).astype(
        float
    )
    return df


def run(run_id: str | None = None, dry_run: bool = False, cache: Path = CACHE_PADRAO) -> str:
    run_id = build_run_id(run_id)
    repo = DeltaRepository(gold_dir=settings.GOLD_DIR, silver_dir=settings.SILVER_DIR)

    df_antes = repo.load_comments()
    df_historico = repo.load_sentiment_history()
    textos = pd.concat(
        [d.loc[d["fonte"] == "comentario", "text"] for d in (df_antes, df_historico)]
    )
    previsoes = _prever_por_texto(textos, cache)

    df_depois = _reclassificar_comentarios(df_antes, previsoes)
    comentarios = df_depois[df_depois["fonte"] == "comentario"].reset_index(drop=True)
    print("[SENTIMENTO] Rotulo pre-treinado (linhas) x rotulo ajustado (colunas):")
    print(
        pd.crosstab(
            comentarios[COLUNA_ROTULO_MODELO], comentarios["sentiment_label"], dropna=False
        )
    )
    if dry_run:
        print("[DRY-RUN] nada foi gravado.")
        return run_id

    ModelEnricher().write_sentiment(
        comentarios, settings.GOLD_SENTIMENT, run_id, preserve_other_fontes=True
    )
    # Historico: a reclassificacao nao e uma medicao nova, entao as linhas
    # existentes sao corrigidas no lugar, mantendo `_run_id`/`_generated_at`.
    write_delta(
        settings.GOLD_SENTIMENT_HISTORY,
        _reclassificar_comentarios(df_historico, previsoes),
        GOLD_SENTIMENT_SCHEMA,
        mode="overwrite",
    )

    topic_scorer = TopicPriorityScorer()
    topic_scorer.write(topic_scorer.score(comentarios), settings.GOLD_TOPIC_PRIORITY_SCORE, run_id)

    content_scorer = ContentTopicPriorityScorer()
    content_scorer.write(
        content_scorer.score(comentarios, repo.load_discourse_topics()),
        settings.GOLD_CONTENT_TOPIC_PRIORITY_SCORE,
        run_id,
    )

    nsm_scorer = NsmScorer()
    nsm_scorer.write(nsm_scorer.score(comentarios, repo.load_profiles()), settings.GOLD_NSM, run_id)

    scorecard = GovernorScorecardScorer()
    scorecard.write(
        scorecard.score(repo.load_profiles(), repo.load_reels(), repo.load_posts(), comentarios),
        settings.GOLD_GOVERNOR_SCORECARD,
        run_id,
    )

    ModelEnricher().write_growth_metrics(
        compute_growth_metrics(repo.load_engagement_history(), repo.load_sentiment_history()),
        settings.GOLD_GROWTH_METRICS,
        run_id,
    )
    return run_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Reclassifica os comentarios com o modelo ajustado (ADR 0049) e recalcula a Gold dependente."
    )
    parser.add_argument("--run-id", default=None, help="run_id desta execucao (default: gerado).")
    parser.add_argument("--dry-run", action="store_true", help="Classifica e mostra, sem gravar.")
    parser.add_argument("--cache", type=Path, default=CACHE_PADRAO, help="Cache das previsoes.")
    args = parser.parse_args()

    run_id = run(run_id=args.run_id, dry_run=args.dry_run, cache=args.cache)
    print(f"[OK] Reclassificacao concluida com run_id: {run_id}")
