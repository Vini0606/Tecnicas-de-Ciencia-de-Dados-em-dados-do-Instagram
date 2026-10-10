"""Orquestração da modelagem: estágio determinístico e refinamento via Gemini"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
from bertopic import BERTopic

from src.features.gold.content_topic_priority_scorer import ContentTopicPriorityScorer
from src.features.gold.model_enricher import ModelEnricher
from src.features.gold.nsm_scorer import NsmScorer
from src.features.gold.topic_priority_scorer import TopicPriorityScorer
from src.logging_setup import attach_run_log_handler
from src.modeling.checkpoint import save_checkpoint
from src.modeling.clustering import cluster_feed_posts, cluster_reels
from src.modeling.comment_sources import combine_comment_sources
from src.modeling.config import GeminiRefinerConfig, ModelingConfig
from src.modeling.gemini_refiner import (
    DEGENERATE_TOPIC_LABEL,
    DISCOURSE_PROMPT_TEMPLATE,
    apply_gemini_refinement,
    is_degenerate_topic,
)
from src.modeling.governor_scorecard import GovernorScorecardScorer
from src.modeling.pca import reduce_dimensions
from src.modeling.post_performance import run_post_performance_stage
from src.modeling.preprocessing import preprocess_comments
from src.modeling.profile_clustering import cluster_governor_profiles
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
    df_post_comments: pd.DataFrame | None = None,
) -> DeterministicModelingResult:
    """Estágio 100% automatizável: PCA -> clustering (reels e posts do feed,
    ADR 0020 Ficha 2) -> sentimento (comentário/legenda/transcrição, ADR
    0020 Ficha 3) -> tópicos de comentário -> Score ICE de priorização de
    tópicos de comentário (ADR 0020 Ficha 6) -> North Star Metric de
    engajamento qualificado por perfil (ADR 0020 Ficha 5) -> tópicos de
    discurso oficial (legenda+transcrição, ADR 0020 Ficha 4) ->
    performance-por-post (representação determinística via KeyBERTInspired,
    não via Gemini) -> clusterização de PERFIL de governador por engajamento
    (Fase 2, ADR 0020) -- roda automaticamente, sem passo manual: antes só saía
    de `scripts/run_profile_clustering_engagement.py`, e a Tela 4 ("Comparar
    perfis", ADR 0021) do dashboard ficava vazia se ninguém lembrasse de
    rodar esse script à parte. Escreve as oito tabelas Gold (clusters,
    sentimento/tópicos provisórios de comentário, Score ICE por tópico, NSM
    por perfil, tópicos de discurso, coeficientes e previsão/resíduo da
    regressão de performance-por-post, clusters de perfil por engajamento)
    sob um único `run_id` novo.

    `parent_run_id`, se informado, é só rastreabilidade -- o `run_id` da
    extração (`coleta.py coletar --modelar`) que disparou esta chamada, gravado
    no checkpoint (ver `save_checkpoint`). Nunca substitui o `run_id` novo
    que esta função sempre cunha para a modelagem (ADR 0001).

    `df_post_comments` (issue #212, opcional): comentários de posts de feed
    (`post_comments_clean`), unidos aos de reels por
    `combine_comment_sources` antes do sentimento -- todos os estágios que
    leem comentários passam a ver as duas origens, discriminadas por
    `origem_comentario` em `governor_sentiment`."""
    run_id = build_run_id(run_id)
    # Handler de arquivo trocado aqui, não na CLI da Coleta -- este é o ponto
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

    df_comments = combine_comment_sources(df_comments, df_post_comments)

    logger.info("[SENTIMENTO] Analisando sentimento dos comentários...")
    df_comments_sentiment = analyze_sentiment(df_comments, config.sentiment)
    df_comments_preprocessed = preprocess_comments(df_comments_sentiment, config.preprocessing)

    logger.info("[TÓPICOS] Ajustando BERTopic...")
    docs = list(df_comments_preprocessed["text_demojized"])
    topic_model, _topics, _probs, document_info = model_topics(docs, config.topics)

    df_comments_final = _merge_topic_info(df_comments_preprocessed, document_info)

    enricher = ModelEnricher()
    # issue #152: `governor_clusters` era uma tabela única discriminada por
    # `content_type`, combinando os dois DataFrames via `pd.concat` antes de
    # uma única escrita -- mas `posts_clean`/`reels_clean` (Silver) se
    # sobrepõem (um Reel também é capturado pelo post-scraper genérico no
    # grid do perfil), então o mesmo post real entrava como 2 linhas dessa
    # tabela, às vezes com `cluster_label` diferente entre os dois
    # pipelines. Duas tabelas Gold separadas, uma por formato, eliminam a
    # sobreposição por construção: os dois clusterings continuam sendo
    # análises legitimamente diferentes sobre o mesmo post, cada uma na sua
    # própria tabela/linha.
    enricher.write_clusters(
        df_reels_clustered.assign(content_type="reel"),
        config.gold_clusters_reels_path,
        run_id,
    )
    enricher.write_clusters(
        df_posts_clustered.assign(content_type="feed"),
        config.gold_clusters_posts_path,
        run_id,
    )
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

    # ADR 0020 (Ficha 6) / issue #91: Score ICE de priorização de tópicos de
    # comentário -- estágio pós-modelagem que só depende de
    # `df_comments_final` (mesmo `governor_sentiment` recém-gravado acima,
    # fonte "comentario"), então roda aqui, antes do bloco de
    # legenda/transcrição abaixo (que é uma fonte diferente, sem tópico de
    # comentário). Inserção isolada de propósito (uma função nova +
    # uma chamada nova): a Ficha 5 (NSM, issue #90) tem a mesma dependência
    # e pode inserir sua própria chamada nesta vizinhança em paralelo --
    # nenhuma das duas precisa do resultado da outra.
    logger.info("[SCORE-ICE] Calculando priorização de tópicos de comentário...")
    topic_priority_scorer = TopicPriorityScorer()
    df_topic_priority = topic_priority_scorer.score(df_comments_final)
    topic_priority_scorer.write(
        df_topic_priority,
        config.gold_topic_priority_score_path,
        run_id,
        generated_at=generated_at,
    )

    # ADR 0020 (Ficha 5) / issue #90: North Star Metric (NSM) de engajamento
    # QUALIFICADO por perfil -- mesma posição/dependência do Score ICE acima
    # (nenhuma das duas precisa do resultado da outra, ver comentário
    # anterior). Lê `df_comments_final` (mesmo `governor_sentiment` recém-
    # gravado, fonte "comentario") e `df_engagement` -- o mesmo parâmetro já
    # recebido por esta função e reutilizado mais abaixo por
    # `run_post_performance_stage` (Gold `governor_engagement`, ver
    # `DeltaRepository.load_profiles`) -- sem nenhuma leitura extra de Gold.
    logger.info(
        "[NSM] Calculando North Star Metric (engajamento qualificado) por perfil..."
    )
    nsm_scorer = NsmScorer()
    df_nsm = nsm_scorer.score(df_comments_final, df_engagement)
    nsm_scorer.write(
        df_nsm,
        config.gold_nsm_path,
        run_id,
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
    discourse_topic_model, _topics_discurso, _probs_discurso, document_info_discurso = (
        model_topics(docs_discourse, config.discourse_topics)
    )
    df_discourse_final = _merge_topic_info(df_discourse_source, document_info_discurso)
    enricher.write_discourse_topics(
        df_discourse_final,
        config.gold_discourse_topics_path,
        run_id,
        generated_at=generated_at,
    )

    # Issue #190 (spec #182): Score ICE por pauta -- provisorio, com os rotulos
    # brutos de discurso; recalculado em `refine_discourse_topics_with_gemini`.
    logger.info("[SCORE-ICE-PAUTAS] Calculando priorizacao de pautas...")
    try:
        content_scorer = ContentTopicPriorityScorer()
        content_scorer.write(
            content_scorer.score(df_comments_final, df_discourse_final),
            config.gold_content_topic_priority_score_path,
            run_id,
            generated_at=generated_at,
        )
    except Exception:
        logger.exception(
            "[SCORE-ICE-PAUTAS] Falha ao calcular/persistir -- etapa pulada, "
            "pipeline segue com os demais estagios."
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

    # Fase 2 (ADR 0020): clusterização de PERFIL de governador por
    # engajamento -- só depende de `df_engagement` (já recebido por esta
    # função, mesmo parâmetro do NSM acima). Mesmo tratamento de falha do
    # bloco de performance-por-post: dado insuficiente (poucos perfis, ou
    # `df_engagement` sem as colunas de `config.profile_cluster.
    # feature_columns`) não pode derrubar os estágios que já rodaram com
    # sucesso -- loga e pula só esta escrita.
    logger.info("[CLUSTER-PERFIL] Agrupando perfis de governador por engajamento...")
    try:
        df_profile_clustered, *_profile_cluster_rest = cluster_governor_profiles(
            df_engagement, config.profile_cluster
        )
        enricher.write_profile_clusters_engagement(
            df_profile_clustered, config.gold_profile_clusters_engagement_path, run_id
        )
    except Exception:
        logger.exception(
            "[CLUSTER-PERFIL] Falha ao clusterizar/persistir -- etapa "
            "pulada, pipeline segue com os demais estágios."
        )

    # ADR 0030 / issue #184: Escore composto (Scorecard) dos governadores --
    # estágio pós-modelagem próprio, roda por último (depende só de insumos
    # já recebidos aqui: engajamento, reels, posts e `df_comments_final`).
    # Mesmo tratamento de falha dos blocos acima: não derruba o que já rodou.
    logger.info("[SCORECARD] Calculando Escore composto dos governadores...")
    try:
        scorecard_scorer = GovernorScorecardScorer()
        df_scorecard = scorecard_scorer.score(
            df_engagement, df_reels, df_posts, df_comments_final
        )
        scorecard_scorer.write(
            df_scorecard,
            config.gold_governor_scorecard_path,
            run_id,
            generated_at=generated_at,
        )
    except Exception:
        logger.exception(
            "[SCORECARD] Falha ao calcular/persistir -- etapa pulada, pipeline "
            "segue com os demais estágios."
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
        # Issue #186: o refino manual via Gemini precisa recarregar o modelo
        # de discurso (antes descartado) e seus documentos.
        discourse_topic_model=discourse_topic_model,
        df_discourse=df_discourse_final,
        discourse_embedding_model_name=config.discourse_topics.embedding_model,
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


@dataclass
class DiscourseRefinementResult:
    df_discourse: pd.DataFrame
    topic_model: BERTopic
    run_id: str


def refine_discourse_topics_with_gemini(
    topic_model: BERTopic,
    docs: list[str],
    df_discourse: pd.DataFrame,
    config: GeminiRefinerConfig,
    run_id: str | None = None,
    df_comments: pd.DataFrame | None = None,
) -> DiscourseRefinementResult:
    """Refina via Gemini os rótulos (`Topic`/`Name`) dos tópicos de discurso
    (assunto das legendas, issue #186) e regrava `governor_discourse_topics`.

    `df_discourse` deve ser o `df_discourse` do checkpoint (mesma ordem de
    linhas que `docs`). O modelo inteiro é refinado (legenda e transcrição
    compartilham o corpus), mas a pauta do dashboard só usa a legenda.

    Tratamentos explícitos (decisões da issue #186): o tópico de ruído
    (`-1`) nunca é refinado como tema -- mantém o `Name` que já tinha; o
    tópico degenerado (sem palavra alguma, ex.: "1____") recebe
    `DEGENERATE_TOPIC_LABEL` em vez de um nome inventado.

    Se `df_comments` (comentarios de `governor_sentiment`) for passado,
    recalcula `content_topic_priority_score` (ICE por pauta, issue #190) com
    os rotulos refinados -- mesmo papel do recalculo do ICE de comentarios em
    `refine_topics_with_gemini`.

    Fora do pipeline automático: só o script manual `scripts/refine_topics.py`
    chama esta função."""
    run_id = build_run_id(run_id)

    degenerate_ids = {
        topic_id
        for topic_id, keywords in topic_model.get_topics().items()
        if topic_id != -1 and is_degenerate_topic(keywords)
    }

    apply_gemini_refinement(topic_model, docs, config, prompt_template=DISCOURSE_PROMPT_TEMPLATE)
    refreshed_info = topic_model.get_document_info(docs).reset_index(drop=True)

    df_refined = df_discourse.reset_index(drop=True).copy()
    topics = refreshed_info["Topic"].values
    names = refreshed_info["Name"].values.copy()
    for i, topic_id in enumerate(topics):
        if topic_id == -1:
            names[i] = df_refined.at[i, "Name"]
        elif topic_id in degenerate_ids:
            names[i] = DEGENERATE_TOPIC_LABEL
    df_refined["Topic"] = topics
    df_refined["Name"] = names

    ModelEnricher().write_discourse_topics(df_refined, config.gold_discourse_topics_path, run_id)

    if df_comments is not None:
        content_scorer = ContentTopicPriorityScorer()
        content_scorer.write(
            content_scorer.score(df_comments, df_refined),
            config.gold_content_topic_priority_score_path,
            run_id,
        )

    return DiscourseRefinementResult(
        df_discourse=df_refined, topic_model=topic_model, run_id=run_id
    )


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

    A escrita de `governor_sentiment` é overwrite só das linhas
    `fonte="comentario"`: as linhas "legenda"/"transcricao" gravadas pela
    modelagem determinística são preservadas (issue #186, que corrigiu a
    antiga limitação em que elas eram apagadas). Tópicos de discurso têm
    refino próprio em `refine_discourse_topics_with_gemini`.

    ATUALIZAÇÃO (ADR 0020 Ficha 6 / issue #91): `topic_priority_score`
    (Score ICE) é recalculado aqui também, a partir de `df_comments_refined`
    -- a ADR 0020 e a issue #91 pedem explicitamente que o Score ICE
    dependa de `governor_sentiment` "já refinado via Gemini", não dos
    rótulos provisórios que `run_deterministic_modeling` grava antes deste
    refinamento existir. A escrita é overwrite (mesma tabela, sem `fonte`
    para discriminar, ao contrário de `governor_sentiment`): o ranking
    provisório calculado em `run_deterministic_modeling` fica obsoleto
    assim que o refinamento roda, exatamente como já acontece com
    `governor_sentiment` acima."""
    run_id = build_run_id(run_id)

    apply_gemini_refinement(topic_model, docs, config)
    refreshed_info = topic_model.get_document_info(docs).reset_index(drop=True)

    df_comments_refined = df_comments.reset_index(drop=True).copy()
    df_comments_refined["Topic"] = refreshed_info["Topic"].values
    df_comments_refined["Name"] = refreshed_info["Name"].values

    ModelEnricher().write_sentiment(
        df_comments_refined,
        config.gold_sentiment_path,
        run_id,
        preserve_other_fontes=True,
    )

    topic_priority_scorer = TopicPriorityScorer()
    df_topic_priority_refined = topic_priority_scorer.score(df_comments_refined)
    topic_priority_scorer.write(
        df_topic_priority_refined, config.gold_topic_priority_score_path, run_id
    )

    return GeminiRefinementResult(
        df_comments=df_comments_refined, topic_model=topic_model, run_id=run_id
    )
