"""Orquestração da modelagem: estágio determinístico e refinamento via Gemini"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
from bertopic import BERTopic

from src.features.gold.model_enricher import ModelEnricher
from src.logging_setup import attach_run_log_handler
from src.modeling.checkpoint import save_checkpoint
from src.modeling.clustering import cluster_feed_posts, cluster_reels
from src.modeling.config import GeminiRefinerConfig, ModelingConfig
from src.modeling.gemini_refiner import apply_gemini_refinement
from src.modeling.pca import reduce_dimensions
from src.modeling.post_performance import run_post_performance_stage
from src.modeling.preprocessing import preprocess_comments
from src.modeling.sentiment import analyze_sentiment
from src.modeling.topics import classify_post_topics, model_topics
from src.run_id import build_run_id

logger = logging.getLogger(__name__)


@dataclass
class DeterministicModelingResult:
    df_reels: pd.DataFrame
    df_comments: pd.DataFrame
    topic_model: BERTopic
    pca_model: object
    cluster_model: object
    cluster_config: dict | None
    cluster_score: float
    cluster_algo_name: str | None
    docs: list[str]
    run_id: str
    parent_run_id: str | None = None


def _build_text_sentiment_source(
    df: pd.DataFrame, id_col: str, text_col: str
) -> pd.DataFrame:
    """Reindexa `df` (posts ou reels da Silver) para o formato que
    `analyze_sentiment`/`ModelEnricher.write_sentiment` esperam -- `id_reel`/
    `text`/`timestamp` mais o que já existir de `inputUrl`/`ownerUsername`/
    `likesCount` (ADR 0020 Ficha 3 / issue #88). Colunas ausentes viram nulo
    em vez de KeyError -- `write_sentiment`/`conform_to_schema` já preenchem
    o resto do schema como nulo, e nem toda chamada (ex.: dado sintético de
    teste) tem todas as colunas de produção.

    `timestamp` sai como string (`data_hora.astype(str)`) porque
    `GOLD_SENTIMENT_SCHEMA` declara esse campo como string -- mesmo tipo já
    usado para o `timestamp` bruto (string) dos comentários -- em vez do
    `datetime64` que `data_hora` tem na Silver de posts/reels.

    `likesCount` sai arredondado para `Int64` (nullable) -- a Silver real
    (`SILVER_POSTS_SCHEMA`/`SILVER_REELS_SCHEMA`) já grava esse campo como
    int64, mas `conform_to_schema` faz cast estrito (sem `safe=False`): um
    valor fracionário vindo de dado sintético de teste faria
    `pa.Table.from_pandas` falhar em vez de truncar silenciosamente."""
    df_source = pd.DataFrame(index=df.index)
    df_source["id_reel"] = df[id_col] if id_col in df.columns else pd.NA
    df_source["text"] = df[text_col] if text_col in df.columns else pd.NA
    for col in ("inputUrl", "ownerUsername"):
        df_source[col] = df[col] if col in df.columns else pd.NA
    df_source["likesCount"] = (
        pd.to_numeric(df["likesCount"], errors="coerce").round().astype("Int64")
        if "likesCount" in df.columns
        else pd.NA
    )
    df_source["timestamp"] = (
        df["data_hora"].astype(str) if "data_hora" in df.columns else pd.NA
    )
    return df_source


def _merge_topic_info(df_comments: pd.DataFrame, document_info: pd.DataFrame) -> pd.DataFrame:
    """Reproduz a junção feita no notebook 03: concatena por posição (não por
    índice) o `document_info` do BERTopic ao DataFrame de comentários, na
    mesma ordem de `docs`, e descarta a coluna `Document` (já redundante com
    `text_demojized`)."""
    df_reset = df_comments.reset_index(drop=True)
    info_reset = document_info.reset_index(drop=True)
    return pd.concat([df_reset, info_reset], axis=1).drop(columns=["Document"])


def run_deterministic_modeling(
    df_reels: pd.DataFrame,
    df_comments: pd.DataFrame,
    df_posts: pd.DataFrame,
    df_engagement: pd.DataFrame,
    config: ModelingConfig,
    run_id: str | None = None,
    parent_run_id: str | None = None,
) -> DeterministicModelingResult:
    """Estágio 100% automatizável: PCA -> clustering (reels e posts do feed,
    ADR 0020 Ficha 2) -> sentimento (comentário/legenda/transcrição, ADR
    0020 Ficha 3) -> tópicos de comentário -> tópicos de discurso oficial
    (legenda+transcrição, ADR 0020 Ficha 4) -> performance-por-post
    (representação determinística via KeyBERTInspired, não via Gemini).
    Escreve as cinco tabelas Gold (clusters, sentimento/tópicos
    provisórios de comentário, tópicos de discurso, coeficientes e
    previsão/resíduo da regressão de performance-por-post) sob um único
    `run_id` novo.

    `parent_run_id`, se informado, é só rastreabilidade -- o `run_id` da
    extração/invocação de `pipeline.py` que disparou esta chamada, gravado
    no checkpoint (ver `save_checkpoint`). Nunca substitui o `run_id` novo
    que esta função sempre cunha para a modelagem (ADR 0001)."""
    run_id = build_run_id(run_id)
    # Handler de arquivo trocado aqui, não em pipeline.py -- este é o ponto
    # onde o run_id da modelagem é de fato cunhado (ADR 0015, decisão 5).
    attach_run_log_handler(run_id, config.logs_dir)
    # Primeira linha do log da modelagem, sempre -- rastreabilidade completa
    # (dados -> modelo) exige que quem abrir só este arquivo, sem checar o
    # checkpoint, já saiba de qual execução esta modelagem veio (ou que não
    # tem uma, se parent_run_id não foi informado).
    logger.debug("parent_run_id: %s", parent_run_id or "nenhum (execução standalone)")

    logger.info("[PCA] Reduzindo dimensionalidade...")
    df_reels_pca, pca_model = reduce_dimensions(df_reels, config.pca)

    logger.info("[CLUSTERING] Agrupando reels...")
    df_reels_clustered, cluster_model, cluster_config, cluster_score, cluster_algo_name = (
        cluster_reels(df_reels_pca, config.cluster)
    )

    # ADR 0020 (Ficha 2 / issue #87): mesma pipeline PCA->AutoClusterHPO
    # aplicada aos posts do feed -- `df_posts` aqui já é só feed
    # (`posts_clean`/`instagram_posts`, granularidade separada de
    # `reels_clean`/`df_reels`, ver `DeltaRepository.load_posts`), então não
    # há filtro de Tipo a fazer antes de clusterizar.
    logger.info("[PCA] Reduzindo dimensionalidade dos posts do feed...")
    df_posts_pca, _pca_feed_model = reduce_dimensions(df_posts, config.pca_feed)

    logger.info("[CLUSTERING] Agrupando posts do feed...")
    df_posts_clustered, *_cluster_feed_rest = cluster_feed_posts(df_posts_pca, config.cluster)

    logger.info("[SENTIMENTO] Analisando sentimento dos comentários...")
    df_comments_sentiment = analyze_sentiment(df_comments, config.sentiment)
    df_comments_preprocessed = preprocess_comments(df_comments_sentiment, config.preprocessing)

    logger.info("[TÓPICOS] Ajustando BERTopic...")
    docs = list(df_comments_preprocessed["text_demojized"])
    topic_model, _topics, _probs, document_info = model_topics(docs, config.topics)

    df_comments_final = _merge_topic_info(df_comments_preprocessed, document_info)

    enricher = ModelEnricher()
    # `content_type` (ADR 0020, Ficha 2) distingue as duas granularidades na
    # mesma tabela `governor_clusters` -- as duas são combinadas antes de
    # uma única escrita (overwrite), para que reels e feed coexistam sem uma
    # sobrescrever a outra.
    df_clusters_combined = pd.concat(
        [
            df_reels_clustered.assign(content_type="reel"),
            df_posts_clustered.assign(content_type="feed"),
        ],
        ignore_index=True,
    )
    enricher.write_clusters(df_clusters_combined, config.gold_clusters_path, run_id)
    # `generated_at` calculado uma vez e repassado às duas escritas de
    # sentimento abaixo, para que governor_sentiment e
    # governor_sentiment_history carimbem o mesmo timestamp -- mesmo
    # raciocínio de EngagementAggregator.aggregate(), que carimba
    # `_generated_at` uma única vez antes de qualquer escrita.
    generated_at = datetime.now(timezone.utc)
    enricher.write_sentiment(
        df_comments_final, config.gold_sentiment_path, run_id, generated_at=generated_at
    )
    # Tabela paralela de histórico, mode=append -- não substitui a tabela
    # acima, que continua overwrite para os consumidores existentes (ver
    # issue #52 / ADR 0017). Deliberadamente não replicado em
    # `refine_topics_with_gemini`: o refinamento só reescreve Topic/Name,
    # sem gerar uma nova medição de sentimento -- gravá-lo no histórico
    # duplicaria pontos próximos no tempo com o mesmo sentiment_label/score.
    enricher.write_sentiment(
        df_comments_final,
        config.gold_sentiment_history_path,
        run_id,
        mode="append",
        generated_at=generated_at,
    )

    # ADR 0020 (Ficha 3) / issue #88: mesmo classificador de sentimento,
    # aplicado também sobre legenda (caption de post) e transcrição (fala do
    # reel, via `includeTranscript`) -- fonte "legenda"/"transcricao"
    # discriminam as linhas na mesma tabela `governor_sentiment`, sempre em
    # append (a primeira escrita, acima, já usou o modo overwrite/default
    # para a fonte "comentario"). Nenhum tópico é calculado para essas duas
    # fontes nesta issue -- fica para a Ficha 4 (BERTopic de discurso),
    # bloqueada por este corpus existir primeiro. Mesmo par de escritas
    # (tabela + histórico) para as duas fontes, só troca o DataFrame de
    # origem/coluna de texto -- feito em loop para não duplicar as quatro
    # chamadas de `write_sentiment`.
    fontes_texto = [
        ("legenda", "legendas", df_posts, "caption"),
        ("transcricao", "transcrições", df_reels, "transcript"),
    ]
    # Acumulado para o estágio de tópicos de discurso logo abaixo (ADR 0020
    # Ficha 4 / issue #89) -- guarda o DataFrame-fonte de ANTES do
    # sentimento (não `df_fonte_sentiment`): tópicos de discurso não
    # dependem de sentimento, então a entrada desse estágio não deve ficar
    # acoplada à forma de saída de um estágio conceitualmente diferente.
    discourse_frames = []
    for fonte, rotulo_log, df_origem, text_col in fontes_texto:
        logger.info("[SENTIMENTO] Analisando sentimento de %s...", rotulo_log)
        df_fonte_source = _build_text_sentiment_source(
            df_origem, id_col="id", text_col=text_col
        )
        df_fonte_sentiment = analyze_sentiment(df_fonte_source, config.sentiment)
        for path in (config.gold_sentiment_path, config.gold_sentiment_history_path):
            enricher.write_sentiment(
                df_fonte_sentiment,
                path,
                run_id,
                mode="append",
                generated_at=generated_at,
                fonte=fonte,
            )
        discourse_frames.append(df_fonte_source.assign(fonte=fonte))

    # ADR 0020 (Ficha 4) / issue #89: mesmo pipeline `model_topics()` já
    # usado para tópicos de comentário, agora sobre o corpus de discurso
    # oficial (legenda+transcrição combinadas num único corpus/modelo, não
    # dois modelos separados) -- tabela Gold própria `governor_discourse_topics`,
    # nunca `governor_sentiment` (decisão de schema já fechada na ADR 0020:
    # granularidades conceitualmente distintas, fala da assessoria vs. reação
    # do público). `config.discourse_topics` usa nr_topics="auto" -- volume
    # baixo (~810 legendas/transcrições na coleta atual) pode legitimamente
    # gerar menos de 50 tópicos estáveis, e isso não deve ser forçado a bater
    # com o modelo de comentários (corpus ~15x maior).
    logger.info("[TÓPICOS-DISCURSO] Ajustando BERTopic sobre legenda+transcrição...")
    df_discourse_source = pd.concat(discourse_frames, ignore_index=True)
    docs_discourse = df_discourse_source["text"].fillna("").tolist()
    _discourse_topic_model, _topics_discurso, _probs_discurso, document_info_discurso = (
        model_topics(docs_discourse, config.discourse_topics)
    )
    df_discourse_final = _merge_topic_info(df_discourse_source, document_info_discurso)
    enricher.write_discourse_topics(
        df_discourse_final,
        config.gold_discourse_topics_path,
        run_id,
        generated_at=generated_at,
    )

    logger.info(
        "[PERFORMANCE-POR-POST] Classificando tema das captions e treinando "
        "Lasso vídeo/estático..."
    )
    try:
        _post_topic_model, df_posts_com_tema = classify_post_topics(df_posts, config.post_topics)
        performance_result = run_post_performance_stage(
            df_posts_com_tema, df_reels, df_engagement, config.post_performance
        )
        enricher.write_post_performance_coefficients(
            performance_result.coefficients,
            config.gold_post_performance_coefficients_path,
            run_id,
        )
        enricher.write_post_performance_predictions(
            performance_result.predictions,
            config.gold_post_performance_predictions_path,
            run_id,
        )
    except Exception:
        # ADR 0019 (parte C), user story 13: dado insuficiente para treinar
        # (ou qualquer outra falha desta etapa) não pode derrubar PCA/
        # clustering/sentimento/tópicos que já rodaram com sucesso na mesma
        # execução -- loga e pula só a escrita Gold desta etapa.
        logger.exception(
            "[PERFORMANCE-POR-POST] Falha ao treinar/persistir -- etapa "
            "pulada, pipeline segue com os demais estágios."
        )

    # Checkpoint incondicional (ver ADR 0003): sem ele, o refinamento via
    # Gemini só poderia rodar no mesmo processo que acabou de ajustar o
    # topic_model — tornar isso opcional reintroduziria a dependência do
    # notebook que essa separação existe para eliminar.
    save_checkpoint(
        run_id,
        topic_model=topic_model,
        df_comments=df_comments_final,
        df_reels=df_reels_clustered,
        pca_model=pca_model,
        pca_feature_columns=config.pca.feature_columns,
        cluster_model=cluster_model,
        cluster_config=cluster_config,
        cluster_score=cluster_score,
        cluster_algo_name=cluster_algo_name,
        embedding_model_name=config.topics.embedding_model,
        checkpoints_dir=config.checkpoints_dir,
        parent_run_id=parent_run_id,
    )

    return DeterministicModelingResult(
        df_reels=df_reels_clustered,
        df_comments=df_comments_final,
        topic_model=topic_model,
        pca_model=pca_model,
        cluster_model=cluster_model,
        cluster_config=cluster_config,
        cluster_score=cluster_score,
        cluster_algo_name=cluster_algo_name,
        docs=docs,
        run_id=run_id,
        parent_run_id=parent_run_id,
    )


@dataclass
class GeminiRefinementResult:
    df_comments: pd.DataFrame
    topic_model: BERTopic
    run_id: str


def refine_topics_with_gemini(
    topic_model: BERTopic,
    docs: list[str],
    df_comments: pd.DataFrame,
    config: GeminiRefinerConfig,
    run_id: str | None = None,
) -> GeminiRefinementResult:
    """Reescreve só os rótulos de tópico (`Topic`/`Name`) de `df_comments`
    com o refinamento manual via Gemini, sob um `run_id` novo — não mexe em
    `governor_clusters`, que não depende do refinamento de tópicos.

    `df_comments` deve ser o `df_comments` retornado por
    `run_deterministic_modeling` (mesma ordem de linhas que `docs`).

    LIMITAÇÃO CONHECIDA (ADR 0020 Ficha 3 / issue #88, não corrigida nesta
    issue): a escrita abaixo usa `fonte="comentario"` (default) em modo
    overwrite -- rodar este refinamento depois de `run_deterministic_modeling`
    substitui `governor_sentiment` inteira só pelas linhas de comentário,
    apagando as linhas "legenda"/"transcricao" que a modelagem determinística
    já tinha gravado nesse mesmo `run_id` de origem. Refinamento via Gemini é
    hoje só sobre tópicos de comentário (ADR 0001) -- religar legenda/
    transcrição nessa escrita fica para quando a Ficha 4 (tópicos de
    discurso) tocar este fluxo.

    ATUALIZAÇÃO (issue #89 / Ficha 4): tópicos de discurso ganharam tabela
    própria (`governor_discourse_topics`, ver `ModelEnricher.write_discourse_topics`)
    e não passam por este refinamento via Gemini -- a limitação acima
    continua não corrigida, deliberadamente fora do escopo da #89 (que não
    toca `governor_sentiment`/refinamento de comentário)."""
    run_id = build_run_id(run_id)

    apply_gemini_refinement(topic_model, docs, config)
    refreshed_info = topic_model.get_document_info(docs).reset_index(drop=True)

    df_comments_refined = df_comments.reset_index(drop=True).copy()
    df_comments_refined["Topic"] = refreshed_info["Topic"].values
    df_comments_refined["Name"] = refreshed_info["Name"].values

    ModelEnricher().write_sentiment(df_comments_refined, config.gold_sentiment_path, run_id)

    return GeminiRefinementResult(
        df_comments=df_comments_refined, topic_model=topic_model, run_id=run_id
    )
