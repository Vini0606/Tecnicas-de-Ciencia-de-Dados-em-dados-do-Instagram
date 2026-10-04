"""
Refina os rotulos de topico de um checkpoint ja gerado por `run_modeling.py`,
via Gemini (GeminiDocsRefiner). Etapa manual e de revisao humana -- decida
quando rodar depois de inspecionar os resultados provisorios em
`governor_sentiment` e `governor_discourse_topics`. Ver ADR 0003.

Alvos (`--target`):
  all        (padrao) topicos de comentario E topicos de discurso (legendas)
  comments   so topicos de comentario (reescreve as linhas `comentario` de
             `governor_sentiment`, preservando legenda/transcricao, e o
             Score ICE de topicos)
  discourse  so topicos de discurso (reescreve `governor_discourse_topics`)

Uso:
  python scripts/refine_topics.py --run-id <run_id>
  python scripts/refine_topics.py --run-id <run_id> --target discourse

Checkpoints gravados antes da issue #186 nao tem o modelo de discurso: com
`--target all` o discurso e pulado (com aviso); com `--target discourse` o
script falha com mensagem clara -- rode `run_modeling.py` de novo para gerar
um checkpoint novo. O script NAO e chamado pelo pipeline automatico.
O refino de discurso recalcula o ICE de pautas (`content_topic_priority_score`,
issue #190) a partir dos comentarios do checkpoint (ja refinados, se `all`).
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.modeling.checkpoint import load_checkpoint, save_checkpoint
from src.modeling.config import GeminiRefinerConfig
from src.modeling.orchestration import (
    refine_discourse_topics_with_gemini,
    refine_topics_with_gemini,
)

TARGETS = ("all", "comments", "discourse")


def run(run_id: str, target: str = "all") -> str:
    if target not in TARGETS:
        raise ValueError(f"target invalido: {target!r}; use um de {TARGETS}.")

    checkpoint = load_checkpoint(run_id)

    refine_comments = target in ("all", "comments")
    refine_discourse = target in ("all", "discourse")
    if refine_discourse and checkpoint.discourse_topic_model is None:
        if target == "discourse":
            raise ValueError(
                f"O checkpoint {run_id!r} nao tem o modelo de topicos de discurso "
                "(gravado antes da issue #186). Rode run_modeling.py de novo para "
                "gerar um checkpoint novo."
            )
        print(
            f"[AVISO] Checkpoint {run_id!r} sem modelo de discurso; "
            "pulando o refino de discurso."
        )
        refine_discourse = False

    api_key = os.getenv("API_GEMINI")
    if not api_key:
        raise ValueError("API_GEMINI nao definida no .env.")

    config = GeminiRefinerConfig(api_key=api_key)

    topic_model = checkpoint.topic_model
    df_comments = checkpoint.df_comments
    discourse_topic_model = checkpoint.discourse_topic_model
    df_discourse = checkpoint.df_discourse
    refinement_run_id = None

    if refine_comments:
        refinement = refine_topics_with_gemini(
            checkpoint.topic_model, checkpoint.docs, checkpoint.df_comments, config
        )
        topic_model = refinement.topic_model
        df_comments = refinement.df_comments
        refinement_run_id = refinement.run_id

    if refine_discourse:
        # Mesmo run_id do refino de comentarios, quando ele roda junto.
        discourse_refinement = refine_discourse_topics_with_gemini(
            checkpoint.discourse_topic_model,
            checkpoint.docs_discourse,
            checkpoint.df_discourse,
            config,
            run_id=refinement_run_id,
            df_comments=df_comments,
        )
        discourse_topic_model = discourse_refinement.topic_model
        df_discourse = discourse_refinement.df_discourse
        refinement_run_id = discourse_refinement.run_id

    # Reescreve o checkpoint em run_id (nao no run_id novo do refinamento):
    # sem isso, o topic_model salvo em disco ficaria com os rotulos
    # provisorios do estagio deterministico para sempre, e o notebook 03
    # mostraria labels desatualizados mesmo depois do refinamento rodar.
    save_checkpoint(
        run_id,
        topic_model=topic_model,
        df_comments=df_comments,
        df_reels=checkpoint.df_reels,
        pca_model=checkpoint.pca_model,
        pca_feature_columns=checkpoint.pca_feature_columns,
        cluster_model=checkpoint.cluster_model,
        cluster_config=checkpoint.cluster_config,
        cluster_score=checkpoint.cluster_score,
        cluster_algo_name=checkpoint.cluster_algo_name,
        embedding_model_name=checkpoint.embedding_model_name,
        parent_run_id=checkpoint.parent_run_id,
        discourse_topic_model=discourse_topic_model,
        df_discourse=df_discourse,
        discourse_embedding_model_name=checkpoint.discourse_embedding_model_name,
    )

    return refinement_run_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Refina os rotulos de topico (comentario e/ou discurso) de um "
            "checkpoint via Gemini (etapa manual, ver ADR 0003)."
        )
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="run_id do checkpoint gerado por run_modeling.py.",
    )
    parser.add_argument(
        "--target",
        choices=TARGETS,
        default="all",
        help="O que refinar: all (padrao), comments ou discourse.",
    )
    args = parser.parse_args()

    refinement_run_id = run(run_id=args.run_id, target=args.target)
    # Sem emoji: o console padrao do Windows usa cp1252 e levanta
    # UnicodeEncodeError ao imprimi-los.
    print(f"[OK] Refinamento via Gemini concluido com run_id: {refinement_run_id}")
