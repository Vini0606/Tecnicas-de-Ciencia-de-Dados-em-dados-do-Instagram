---
status: accepted
---

# `pipeline.py` como ponto único das tabelas do dashboard: UGC no extrator, comentários de posts, janela de coleta e relatório de tabelas

## Contexto

Subir e validar o dashboard a partir de um clone vazio (`data/` não é versionada) exigia combinar o
`pipeline.py` com scripts avulsos, e não havia como saber se a execução tinha coberto todas as tabelas.
A spec #210 levantou quatro problemas.

1. **UGC fora do pipeline.** `governor_ugc_mentions`, lida pelo estágio Engage do Funil
   ([ADR 0032](0032-funil-em-escala-logaritmica-com-engage-do-ugc-piloto-e-comparativo-vs-mediana.md)),
   só saía de `scripts/run_ugc_mentions.py`. O script tinha função de ingestão própria
   (`extract_and_land_ugc_mentions`) e cadência própria, decisão da issue #93 / ADR 0020 (Ficha 8).
2. **Comentários de posts descartados.** O `apify/instagram-post-scraper` retorna `latestComments`, mas
   `BRONZE_POSTS_SCHEMA` não tinha a coluna. Sentimento, tópicos, NSM, ICE, Convert do Funil e Qualidade
   do Scorecard só viam comentários de reels.
3. **Coleta rasa.** O `pipeline.py` só coletava os 30 itens mais recentes por perfil, o que cobre poucas
   semanas. Com isso, a Consistência do Scorecard ([ADR 0030](0030-escore-composto-scorecard-com-consistencia-por-cmgr-de-engajamento-por-data-de-publicacao.md))
   ficava pendente para todos. A janela de dias só existia no backfill, e não havia como forçar uma coleta
   nova com a Bronze já populada.
4. **Sem validação do resultado.** Estágios de modelagem com exceção engolida e tabelas `overwrite`
   desatualizadas apareciam no dashboard sem aviso, porque os loaders degradam para `DataFrame` vazio em
   silêncio.

## Decisão

1. **UGC no extrator unificado, sem flag** (issue #211). `extract_and_land` coleta perfis → posts → reels
   → UGC sob o mesmo `run_id`, arquivando cada JSON na landing zone antes da Bronze.
   - O UGC é a **última** coleta e é **tolerante a falha**: exceção do actor, lista vazia ou Bronze sem
     caminho de UGC viram `ugc_error` no retorno, sem descartar as demais entidades. Perfis, posts e reels
     continuam fail-fast.
   - O `pipeline.py` grava a Silver e a Gold de UGC a cada execução, inclusive com Bronze reaproveitada.
   - O teto por perfil é o mesmo das outras coleções.
   - `extract_and_land_ugc_mentions` e `scripts/run_ugc_mentions.py` foram removidos.
   - Isto **supera** a decisão de "script standalone com cadência própria" da issue #93 / ADR 0020
     (Ficha 8). O restante da Ficha 8 (actor, schema, separação orgânico × publi) segue valendo.
2. **Comentários de posts em Silver separada** (issue #212).
   - A Bronze de posts guarda `latestComments`; o append com `schema_mode="merge"` dispensa migração.
   - `CommentCleaner(origem="post")` grava `post_comments_clean` (`id_post`), separada de
     `comments_clean` (reels), para as duas origens poderem ser analisadas à parte.
   - Na modelagem, `combine_comment_sources` une as duas, renomeia `id_post` → `id_reel` e deduplica por
     `id_comment` **preferindo a linha de reel**. Um reel também aparece no scraper de posts (issue #152),
     e a linha de reel preserva os joins com `governor_clusters_reels`/`reels_clean`.
   - `governor_sentiment` e `governor_sentiment_history` ganham `origem_comentario` (`reel`/`post`, nulo em
     legenda/transcrição). `fonte` continua `comentario`, então o dashboard não muda.
3. **Janela, teto e extração forçada no `pipeline.py`** (issue #213).
   - Flags: `--days N` (`onlyPostsNewerThan` em posts, reels e UGC), `--results-limit M` e
     `--force-extract`.
   - `--days` **implica extração real**; sem isso, a Bronze em cache faria a janela ser ignorada em
     silêncio.
   - Teto efetivo: `--results-limit`, senão `default_results_limit(days)` (max(200, 10 × N)), senão
     `RESULTS_LIMIT`.
   - Custo estimado: sem janela, as três coleções pelo teto; com janela, posts+reels pela taxa calibrada e
     UGC pelo teto. Qualquer extração continua exigindo `--yes`.
   - Não está confirmado que o `apify/instagram-tagged-scraper` aceita `onlyPostsNewerThan`. Por isso, com
     `--days`, a Silver de UGC descarta posts anteriores à janela como salvaguarda.
4. **Relatório de tabelas e código de saída** (issue #214). `src/pipeline_report.py` declara o catálogo
   `TABELAS_ESPERADAS` e classifica cada tabela, nesta precedência: NÃO SOLICITADA (estágio não rodou) >
   AUSENTE > DESATUALIZADA > VAZIA > OK.
   - DESATUALIZADA significa que o último commit Delta é anterior ao início da execução. O frescor é
     medido pelo **commit Delta**, não pelo `_run_id`: a Silver herda o `_run_id` da Bronze e a modelagem
     cunha um próprio.
   - O processo sai com **1** se alguma tabela **lida pelo dashboard**, de estágio executado, não estiver
     OK. As demais (por exemplo `post_performance_*`, que a ADR 0019 pula com pouco dado) aparecem como
     aviso.
   - Um teste estático amarra o catálogo às tabelas que as Telas leem.
5. **O refino via Gemini continua manual** (ADR 0001). Não entra no `pipeline.py`.

## Consequências

- Um clone vazio sobe o dashboard com `uv run python pipeline.py --yes --run-modeling [--days N]`, e o
  relatório final diz se todas as tabelas do dashboard foram geradas.
- Os números de Convert, NSM, Qualidade, ICE e grupos de comentários mudam em relação ao dado de
  2026-10-04 citado nas ADRs 0030–0032, porque passam a contar também a reação em posts. O tempo de
  sentimento e do BERTopic de comentários cresce com o volume.
- `id_reel` em `governor_sentiment` passa a significar "id da publicação comentada" (reel ou post). A coluna
  não foi renomeada, para não quebrar os consumidores.
- Com o teto padrão (30), a contagem de UGC deixa de saturar no teto do piloto (5), e o comparativo do
  Engage aparece sozinho (ADR 0032, item 5). Continuam abertas, da ADR 0032, a janela de tempo do Engage e
  a mediana em "Todos os Governadores".
- **Risco de custo:** com `--days`, o teto padrão também vale para o UGC. Se o actor de UGC ignorar a
  janela, o custo dele cresce com o teto. Mitigação: `--results-limit` explícito. Um teto próprio para UGC
  fica como decisão futura.
- **Risco operacional no caminho serverless:** a Lambda `extract` ganha mais uma chamada síncrona de actor
  com o mesmo timeout de 300 s (Terraform não alterado). As Lambdas `transform`/`load` ainda não gravam
  Silver/Gold de UGC nem comentários de posts, e o caminho serverless segue sem paridade com o pipeline
  local.
- **Confirmado com dado real (2026-10-06, issue #216):** o `apify/instagram-tagged-scraper` **respeita**
  `onlyPostsNewerThan`. Com `--days 5`, 233 dos 234 itens com data estavam dentro da janela; o único fora
  ficou por pouco além da borda. A salvaguarda `filtrar_ugc_por_janela` continua como defesa, sem efeito
  prático. Nessa coleta (26 governadores, teto 30), o actor devolveu 246 itens (~US$ 0,57), 12 deles
  itens de erro sem `id` (governador sem marcação no período), descartados pelo cleaner, e nenhum perfil
  bateu no teto.
