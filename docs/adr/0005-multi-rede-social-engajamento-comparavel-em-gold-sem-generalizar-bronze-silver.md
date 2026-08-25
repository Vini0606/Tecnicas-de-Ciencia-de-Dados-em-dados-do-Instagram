---
status: accepted
---

# Preparar a metodologia para múltiplas redes sociais com engajamento comparável em Gold, sem generalizar Bronze/Silver nem agir agora

## Contexto

O roadmap do projeto (registrado no `/handoff`) inclui uma frente de "multi-rede-social": estender a coleta/análise, hoje restrita ao Instagram, para outras redes onde os governadores têm presença. Ao contrário da frente de multi-entidade (ver [ADR 0004](0004-manter-pipelines-separados-por-entidade-sem-generalizar-schema-agora.md)), aqui o "quem" não muda — são os mesmos 27 governadores já cobertos hoje — só a origem do dado.

O Instagram está amarrado profundamente na camada de coleta e dado bruto: `InstagramScraper` (`src/data_extract/scraper.py`) usa IDs de Actor da Apify específicos do Instagram (`apify/instagram-post-scraper`, `apify/instagram-reel-scraper`), e os schemas Bronze/Silver (`BRONZE_POSTS_SCHEMA`, `BRONZE_REELS_SCHEMA`, `SILVER_COMMENTS_SCHEMA`, etc.) modelam formatos de conteúdo nativos do Instagram — "reels" é terminologia própria do Instagram/Facebook, sem equivalente direto em outras redes.

Já a camada Gold de engajamento (`GOLD_ENGAGEMENT_SCHEMA`, populada por `EngagementAggregator`) já é bem mais genérica: `followersCount`, `likesSum`, `commentsSum`, `% ENGAJAMENTO`, `RECENCIA`, `FREQUENCIA` são conceitos presentes, com nomes próprios mas equivalentes, em praticamente qualquer rede social (Twitter/X, TikTok, YouTube, Facebook).

## Decisão

- O objetivo é permitir **comparar o mesmo governador entre redes sociais** (ex.: engajamento ou sentimento no Instagram vs. em outra rede) — não pipelines isolados sem relação entre si.
- Essa comparabilidade é resolvida **só na camada Gold**: cada rede social manteria seu próprio scraper e seus próprios schemas Bronze/Silver, refletindo o formato de conteúdo nativo daquela rede. Uma tabela Gold de engajamento comum, com uma dimensão de rede social, seria alimentada por agregadores adaptados por rede.
- **Nenhuma mudança de código acontece agora.** `InstagramScraper`, `schemas_delta.py` e `EngagementAggregator` continuam como estão até que uma segunda rede social seja de fato integrada. O nome exato da coluna de rede social, os valores possíveis, e como cada agregador por rede alimenta a tabela comum ficam para quando essa integração for real.

## Por que

O dado bruto de cada rede social é moldado pelo formato de conteúdo específico dela — forçar um "post genérico" desde a entrada perderia informação nativa relevante (ex.: retweets no Twitter/X, duração de vídeo no TikTok) sem necessidade, já que quem precisa ser comparável entre redes é a métrica agregada, não o dado bruto. A comparabilidade cabe em Gold porque o schema de engajamento já é, na prática, agnóstico de rede.

Não agir agora segue o mesmo raciocínio do ADR 0004: sem uma segunda rede social concreta escolhida, decidir o nome da coluna, os valores possíveis, e a forma exata de agregação por rede é desenho especulativo. É mais barato validar esse desenho contra uma integração real do que manter um campo "morto" em produção, preenchido só com um único valor (`instagram`) por tempo indeterminado.

## Opções consideradas

- **Pipelines totalmente independentes por rede, sem comparação** — rejeitada: diferente do caso de multi-entidade, aqui o "quem" é o mesmo (os 27 governadores já cobertos), a chave de join já existe e é estável — descartar a comparabilidade jogaria fora o principal valor analítico de ter múltiplas redes para o mesmo governador.
- **Generalizar também Bronze/Silver num formato de "post genérico" único** — rejeitada: o formato nativo de cada rede carrega informação que um schema genérico perderia (retweets, duração de vídeo, etc.), e nada exige que o dado bruto seja comparável — só o agregado em Gold precisa ser.
- **Adiantar a coluna `rede_social` (ou equivalente) no `GOLD_ENGAGEMENT_SCHEMA` já agora** — rejeitada por ora: sem uma segunda rede real para validar o desenho, o nome da coluna, os valores possíveis e a forma de agregação por rede seriam decisões especulativas, com risco de precisar de retrabalho quando a integração real acontecer.

## Consequências

- A tabela `governor_engagement` continua representando só Instagram até que uma segunda rede seja de fato integrada — nenhuma comparação entre redes é possível hoje.
- Quando uma segunda rede social for implementada, o trabalho de generalizar `GOLD_ENGAGEMENT_SCHEMA` (dimensão de rede social) e adaptar `EngagementAggregator` precisa ser feito do zero — este ADR não adianta nenhuma dessas peças, só documenta que a intenção de deixá-las comparáveis, e não isoladas, foi deliberada.
- Bronze e Silver continuarão a crescer com um scraper e um conjunto de schemas por rede social — não há intenção de convergir o dado bruto para um formato único, mesmo depois de uma segunda rede ser adicionada.
