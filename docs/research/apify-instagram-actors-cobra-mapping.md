# Apify Instagram Actors × COBRA — Mapeamento de Opções

**Data da pesquisa:** 2026-09-08
**Escopo:** Levantamento de actors do Apify Store para Instagram, comparados ao baseline em uso no pipeline, e mapeados ao framework COBRA (Muntinga 2011: Consuming / Contributing / Creating) cruzado com funil RACE. Este documento **não decide** qual actor adotar — apenas documenta o que cada um oferece, com fonte primária, para suportar a decisão no TCC.

**Método:** cada actor foi consultado diretamente na sua página do Apify Store (abas Overview/Input/API), via `WebFetch`. Quando a página é um alias de SEO (`apify.com/store/<slug>/<slug>`), o documento cita a página canônica do actor (`apify.com/<dev>/<actor-name>`) para a qual o alias aponta, confirmada via a Apify API pública (`api.apify.com/v2/acts/<id>`) quando possível. Todo campo listado é citado literalmente como aparece na fonte; quando uma informação não pôde ser confirmada por fonte primária, isso é declarado explicitamente em vez de inferido.

---

## 0. Baseline atual (para referência, não re-verificado além do código)

Do `src/data_extract/scraper.py`:

| Papel | Actor ID usado | Confirmado nesta pesquisa |
|---|---|---|
| Perfis | `shu8hvrXbJbY3Eb9W` | **É o actor genérico `apify/instagram-scraper`** ("👁 Instagram Scraper"), não um profile-scraper dedicado — confirmado via `api.apify.com/v2/acts/shu8hvrXbJbY3Eb9W` → `{"id":"shu8hvrXbJbY3Eb9W","name":"instagram-scraper","username":"apify"}`. O pipeline hoje o usa apenas no modo perfil (`resultsType: "details"`), mas o mesmo actor **também suporta** `resultsType: "mentions"` e `"comments"` e busca por hashtag/perfil (`search`/`searchType`) — capacidades não exploradas hoje. Fonte: `https://apify.com/apify/instagram-scraper/input-schema`. |
| Posts | `apify/instagram-post-scraper` | Confirmado, ver §1.1. |
| Reels | `apify/instagram-reel-scraper` | Confirmado, ver §1.2. |
| Comentários | *(nenhum dedicado — vêm embutidos em `latestComments` do reel-scraper, amostra de ~10)* | Confirmado como amostra limitada, ver §1.2 e §2.1. |

**Achado relevante para a decisão:** como o actor de perfis já usado (`shu8hvrXbJbY3Eb9W` = `apify/instagram-scraper`) é o actor "canivete suíço" da Apify, ele **já é tecnicamente capaz** de resolver hashtag search e mentions search sem trocar de actor — bastaria mudar o `run_input` (`resultsType`/`search`/`searchType`) nas chamadas existentes. Isso muda o trade-off: para hashtag/mentions, a opção mais barata em complexidade de integração pode ser reconfigurar o actor já integrado, não adicionar um novo.

---

## 1. Post/Reel scrapers (comparação com os 2 já em uso)

### 1.1 `apify/instagram-post-scraper` (baseline atual)
- **URL:** https://apify.com/apify/instagram-post-scraper
- **Dev:** Apify (oficial)
- **Preço:** pay-per-event, "$1.00 / 1,000 posts" (plano Free: "$2.70 per 1,000 results"). Fonte: `https://apify.com/apify/instagram-post-scraper/input-schema`.
- **Input schema:** `username` (array), `resultsLimit` (int, "Maximum number of posts you want to scrape per profile"), `skipPinnedPosts` (bool), `onlyPostsNewerThan` (string), `dataDetailLevel` (string — "Choose the data package you want to extract").
- **Output (exemplo JSON, aba API):** `id`, `shortCode`, `url`, `inputUrl`, `caption`, `type`, `hashtags`, `mentions`, `alt`, `likesCount`, `commentsCount`, `videoViewCount`, `videoPlayCount`, `displayUrl`, `images`, `videoUrl`, `dimensionsHeight`, `dimensionsWidth`, `videoDuration`, `productType`, `ownerUsername`, `ownerFullName`, `ownerId`, `taggedUsers`, `coauthorProducers`, `timestamp`, `isPinned`, `isSponsored`, `isCommentsDisabled`, `childPosts`, `firstComment`, `latestComments`, `musicInfo`.
- **Não contém:** `sharesCount`/`reshareCount` explícito, nem contagem de "saves". `latestComments` é amostra, não total.
- Fonte: `https://apify.com/apify/instagram-post-scraper/api`, `https://apify.com/apify/instagram-post-scraper/input-schema`.

### 1.2 `apify/instagram-reel-scraper` (baseline atual)
- **URL:** https://apify.com/apify/instagram-reel-scraper
- **Dev:** Apify (oficial)
- **Preço:** pay-per-event, "from $1.00 / 1,000 reels". Fonte: `https://apify.com/apify/instagram-reel-scraper` (aba principal) e `/input-schema`.
- **Input schema:** `username` (array), `resultsLimit` (int), `onlyPostsNewerThan` (string), `skipPinnedPosts` (bool), `skipTrialReels` (bool), **`includeSharesCount`** (bool — "Extract share counts", descrito como **exigindo plano Starter ou superior**), `includeTranscript` (bool, cobrado por minuto), `includeDownloadedVideo` (bool, cobrado por MB).
- **Output:** `likesCount`, `commentsCount`, `videoViewCount`, `videoPlayCount`, `sharesCount` (quando habilitado), `caption`, `hashtags`, `mentions`, `taggedUsers`, id/URL/shortCode/type, `videoUrl`, `downloadedVideo` (URL), `audioUrl`, `images`, `videoDuration`, `displayUrl`, dimensões, `timestamp`, `ownerUsername`, `ownerFullName`, `ownerId`, `productType`, `locationName`, `locationId`, **`latestComments`** (10 por reel, com replies/likes/timestamps — amostra, não total), `transcript`, `musicInfo`, `paidPartnership`/`sponsors`/`coauthorProducers`, `isCommentsDisabled`, `isPinned`.
- **Achado chave:** o próprio actor em uso **já suporta `sharesCount`** via flag de input (`includeSharesCount`) — feature paga (Starter+), atualmente não habilitada no `run_input` do código (`scraper.py` só define `resultsLimit`). Isso é uma mudança de configuração, não de actor, para capturar "shares" no nível Contributing.
- Fonte: `https://apify.com/apify/instagram-reel-scraper/input-schema`, `https://apify.com/apify/instagram-reel-scraper`.

### 1.3 Actor genérico `apify/instagram-scraper` ("👁 Instagram Scraper")
- **URL:** https://apify.com/apify/instagram-scraper
- **Dev:** Apify (oficial). 387.345 usuários totais, 190M+ execuções, nota 4.72/5 (592 reviews) — fonte: `api.apify.com/v2/acts/apify~instagram-scraper` e página do actor.
- **Preço:** não detalhado explicitamente na página consultada (modelo pay-per-event geral da linha Apify Instagram, "$5 grátis/mês"); não confirmado valor exato por resultado.
- **Input schema:** `resultsType` (posts | reels | comments | mentions | details — descrito literalmente como "Posts returns a feed of content. Profile, hashtag, or place details returns metadata"), `directUrls` (array), `resultsLimit` (int), `onlyPostsNewerThan` (string), `search` (string — busca por hashtag/perfil/local), `searchType` (string), `searchLimit` (int), `addParentData` (bool — adiciona campo `dataSource` indicando origem `profile` ou `hashtag`).
- **Capacidade não usada hoje:** já suporta `resultsType: "mentions"` (posts em que o perfil-alvo foi marcado por terceiros) e `resultsType: "comments"`, além de busca por hashtag via `search`/`searchType`.
- Fonte: `https://apify.com/apify/instagram-scraper/input-schema`.

---

## 2. Comment scrapers dedicados

### 2.1 `apify/instagram-comment-scraper` ("📝 Instagram Comments Scraper")
- **URL:** https://apify.com/apify/instagram-comment-scraper (a URL de SEO `apify.com/store/comment-scraper/scrape-instagram-comments` aponta para este mesmo actor)
- **Dev:** Apify (oficial). 52.613 usuários totais, 4.760 mensais, 4.66/5 (fonte: página do actor).
- **Preço:** pay-per-event, **"$1.90 / 1.000 comentários"** (plano Free: "$2.30 per 1,000 results"). Fonte: `https://apify.com/apify/instagram-comment-scraper`.
- **Input schema:** `directUrls` (array de URLs de post/reel), **`resultsLimit`** (int) — descrito literalmente: *"Set the number of comments you expect to scrape from each post or reel. If set to 5, you will get 5 comments per URL."* Não há valor máximo ou default declarado na página. **`includeNestedComments`** (bool) — descrito literalmente: *"This feature is for paying users only. If checked, the scraper will extract replies for each comment."* Fonte: `https://apify.com/apify/instagram-comment-scraper/input-schema`.
- **Output:** `id`, `text`, `ownerUsername`, `ownerProfilePicUrl`, `timestamp`, `likesCount`, `repliesCount`, `replies` (array aninhado).
- **Diferença crítica vs. baseline:** este actor busca **por post/reel**, com `resultsLimit` configurável (não fixo em ~10 como o `latestComments` embutido no reel-scraper) — ou seja, dá controle explícito sobre quantos comentários puxar por post, incluindo replies/threads (feature paga). Ainda assim, a página não confirma que existe forma de puxar o **total absoluto** de comentários de um post — apenas "quantos você espera" via `resultsLimit`, o que sugere que acima de um certo volume o scraping pode ainda ser limitado pela paginação real do Instagram (não confirmado/incerto — não há declaração explícita de limite técnico máximo na página consultada).

---

## 3. Profile scrapers (comparação com o atual)

### 3.1 `apify/instagram-profile-scraper` ("👤 Instagram Profile Scraper") — dedicado
- **URL:** https://apify.com/apify/instagram-profile-scraper
- **Dev:** Apify (oficial). 212.743 usuários totais, 4.75/5.
- **Preço:** pay-per-event, **"$1.60 / 1.000 perfis"**.
- **Input schema:** `usernames` (array), `includeAboutSection` (bool, feature paga).
- **Output:** `username`, `fullName`, `id`, `url`, `inputUrl`, `biography`, `private`, `verified`, `profilePicUrl`, `profilePicUrlHD`, `followersCount`, `followsCount`, `postsCount`, `igtvVideoCount`, `highlightReelCount`, `videosCount`, `isBusinessAccount`, `businessCategoryName`, `externalUrl`, `externalUrls` (array), `joinedRecently`, `hasChannel`, `relatedProfiles` (array), `latestPosts` (12 posts com métricas), `latestIgtvVideos` (12 vídeos com views). Seção paga adicional (`includeAboutSection`): `date_joined`, `date_verified`, `country`, `former_usernames` (contagem), `accounts_with_shared_followers`.
- Fonte: `https://apify.com/apify/instagram-profile-scraper`.

**Comparação com o atual (`shu8hvrXbJbY3Eb9W` = `apify/instagram-scraper` em modo `details`):** o dedicado retorna explicitamente `businessCategoryName`, `isBusinessAccount`, `relatedProfiles`, `highlightReelCount`, e (pago) `date_joined`/`date_verified`/`former_usernames`/`accounts_with_shared_followers` — campos de categorização e "about" que não foram confirmados no schema do actor genérico atual (a página do genérico, consultada em `resultsType: details`, descreve apenas "bio, followers, posts count, verified and business status" em prosa, sem listar todos os campos individualmente — **incerto** se `businessCategoryName`/`relatedProfiles` também saem do actor genérico; não confirmado por fonte primária nesta pesquisa).

### 3.2 Followers/growth history (não confirmado no schema do baseline)
Ver §5 abaixo — tratado separadamente porque nenhum dos dois (`apify/instagram-scraper` genérico ou `apify/instagram-profile-scraper`) declara manter histórico de séries temporais entre execuções; ambos retornam um snapshot no momento da chamada.

---

## 4. Hashtag scraper — capacidade geral (ver §6 para o recorte de UGC/Creating)

### 4.1 `apify/instagram-hashtag-scraper` ("#️⃣ Instagram Hashtag Scraper")
- **URL:** https://apify.com/apify/instagram-hashtag-scraper
- **Dev:** Apify (oficial). 105.809 usuários totais, 8.756 mensais, 3.39/5 (nota mais baixa entre os actors oficiais de Instagram pesquisados).
- **Preço:** pay-per-event, **"$1.90 / 1.000 resultados"** (plano Free: "$2.60 per 1,000 results").
- **Input schema:** `hashtags` (array), `keywordSearch` (bool), `resultsType` (posts | reels), `resultsLimit` (int).
- **Output:** `id`, `shortCode`, `url`, `type`, `inputUrl`, `likesCount`, `commentsCount`, **`reshareCount`** (confirmado no exemplo: `"reshareCount": 17` — descrito como "número de vezes que o reel/post foi compartilhado", aparece nos exemplos de reels), `videoPlayCount`, `igPlayCount`, `fbLikeCount`, `fbPlayCount`, `caption`, `hashtags`, `mentions`, `taggedUsers`, `timestamp`, `locationName`, `locationId`, `displayUrl`, `images`, `videoUrl`, `videoDuration`, `childPosts`, dimensões, `ownerUsername`, `ownerId`, `ownerFullName`, `productType`, `musicInfo`, `firstComment`, `latestComments`, `isCommentsDisabled`, `isPinned`.
- Fonte: `https://apify.com/apify/instagram-hashtag-scraper`.

---

## 5. Follower/growth history actors

### 5.1 `afanasenko/instagram-follower-tracker` ("Instagram Follower Tracker")
- **URL:** https://apify.com/afanasenko/instagram-follower-tracker
- **Dev:** Andrey Afanasenko (community)
- **Preço:** pay-per-event, **"from $0.04 / 1.000 followers"** (varia por tier: Free $0.01, Bronze $0.05, Diamond $0.03/1000), com cobrança mínima de 10.000 followers por execução.
- **Input schema:** `usernames`, `trackFollowers` (bool, default on), `trackFollowing` (bool), `engagementAudit` (bool — "find top fans and ghost followers"), `notificationEmail`, `automaticFirstComparison` (beta paga).
- **Output:** `target_username`, `change_type` ("tracked"/"new"/"lost"), `list_type` ("followers"/"following"), `username`, `full_name`, `profile_pic_url`, `is_verified`, `is_private`, `detected_at`.
- **Achado importante:** **não** armazena série histórica de contagem de seguidores ao longo do tempo — mantém apenas o snapshot mais recente num key-value store interno para comparar contra a execução anterior e sinalizar ganhos/perdas individuais. Ou seja, resolve "quem entrou/saiu" mas não "curva de crescimento ao longo do tempo" de forma nativa — isso teria que ser reconstruído rodando o actor periodicamente e persistindo os deltas na tabela `governor_engagement_history` já existente no pipeline.
- Fonte: `https://apify.com/afanasenko/instagram-follower-tracker`.

### 5.2 `gordian/instagram-profile-history` ("Instagram Profile History")
- **URL:** https://apify.com/gordian/instagram-profile-history
- **Dev:** Gordian (community — "agência de web scraping fundada por Louis Deconinck", conforme a própria página)
- **Preço:** pay-per-event, "$1.00 / 1.000 resultados"
- **Uso:** 247 usuários totais, **apenas 10 mensais**, sem avaliações ("No ratings yet") — sinal de adoção baixa/risco de manutenção, não confirmado se é ativamente mantido.
- **Input schema:** `accounts` (array)
- **Output (exemplo JSON):** `profile_history_points` (array de snapshots diários: `date`, `followers_count`, `follows_count`, `media_count`, `engagement_rate`, `average_likes`, `average_comments`), `growth_stats` (taxas de crescimento trimestrais/semanais), `score` (qualidade/autenticidade do perfil).
- **Diferença vs. 5.1:** este é o único actor pesquisado que **declara nativamente** série temporal (`profile_history_points`, múltiplas entradas datadas de nov–dez/2025 no exemplo) em vez de apenas diff entre duas execuções — mas com adoção muito baixa (10 usuários/mês), o que é um risco de confiabilidade/suporte a considerar frente ao ADR de "Backfill lambda propagation" já pendente no projeto.
- Fonte: `https://apify.com/gordian/instagram-profile-history`.

**Observação geral de §5:** dado que a tabela `governor_engagement_history` já existe no pipeline e presumivelmente já acumula snapshots do próprio scraper de perfil a cada execução, um actor de histórico externo pode ser redundante — a decisão real pode ser "rodar o profile-scraper existente com mais frequência e granularidade" vs. "adotar um actor de terceiros que promete fazer isso nativamente mas tem baixíssima adoção".

---

## 6. Stories (formato ausente do pipeline hoje)

### 6.1 `automation-lab/instagram-stories-scraper` ("Instagram Stories Scraper — Stories & Highlights")
- **URL:** https://apify.com/automation-lab/instagram-stories-scraper
- **Dev:** Stas Persiianenko (automation-lab, community). 329 usuários totais, 52 mensais, 4.0/5.
- **Preço:** pay-per-event, **"$1.20 / 1.000 stories"** + "$0.005 por início de execução" (varia por tier: Diamond $0.00056/story, Free $0.0023/story).
- **Input schema:** `usernames` (array), **`sessionCookie`** (string — **requer autenticação/login no Instagram**), `includeHighlights` (bool), `maxHighlights` (int), `includeProfile` (bool), `proxyConfiguration`.
- **Output:** `storyId`, `userId`, `username`, `profileUrl`, `mediaType`, `mediaUrl`, `thumbnailUrl`, `timestamp`, `expiresAt`, `durationSecs`, `caption`, `isHighlight`, `highlightId`, `highlightTitle`, `musicArtist`, `musicTitle`, `hasLink`, `linkUrl`, `stickerTypes` (array), `viewerCount`, `scrapedAt`.
- **Risco relevante:** exige `sessionCookie` de uma conta real do Instagram — implica risco de ToS/banimento de conta e gestão de credenciais, diferente dos demais actors pesquisados (que operam sem login).

### 6.2 `datavoyantlab/advanced-instagram-stories-scraper` ("Advanced Instagram Stories Scraper (Fast)")
- **URL:** https://apify.com/datavoyantlab/advanced-instagram-stories-scraper
- **Dev:** DataVoyantLab (community)
- **Preço:** "$0.099 por execução" + **"$3.00 / 1.000 usernames"** (~$3.99 para 1.000 perfis, conforme exemplo da própria página)
- **Sem login necessário** — declarado explicitamente: acessa "apenas stories publicamente disponíveis", sem exigir credenciais do Instagram. Diferença chave vs. 6.1.
- **Input schema:** `usernames` (array)
- **Output:** `taken_at`, `pk`, `id`, `media_type`, `original_width`, `original_height`, `image_versions2` (URLs em múltiplas resoluções), `user` (username, verificação, foto de perfil), `story_link_stickers`, `story_hashtags`, `caption`, `product_type`.
- Fonte: `https://apify.com/datavoyantlab/advanced-instagram-stories-scraper`.

**Nota:** existem outros actors de stories no Apify Store (`gordian/instagram-story-scraper`, `codenest/instagram-story-scraper`, `muhammetakkurtt/instagram-scraper`) identificados via busca mas **não abertos/confirmados por fonte primária nesta pesquisa** — listados aqui apenas como pistas para investigação futura, não como achados confirmados.

---

## 7. Mentions/Tagged posts scrapers — SEÇÃO CRÍTICA PARA "CREATING"/UGC

O usuário pediu foco específico nesta frente: **volume/engajamento de UGC** — conteúdo criado por terceiros (seguidores) que marca, menciona ou usa hashtag do perfil do governador — não conteúdo publicado pelo próprio perfil. Isto é o núcleo do nível **Creating** do COBRA.

### 7.1 Existe actor dedicado a "posts onde @perfil foi marcado por terceiros"? **Sim, confirmado.**

#### `apify/instagram-tagged-scraper` ("🔖 Instagram Mentions and Tagged Posts Scraper")
- **URL:** https://apify.com/apify/instagram-tagged-scraper
- **Dev:** Apify (oficial). **9.999 usuários totais, 575 mensais, 100% success rate, 5.0/5 estrelas, 107 bookmarks** — melhor sinal de confiabilidade/adoção entre os actors de mentions/tagged pesquisados.
- **Preço:** pay-per-event, **"$1.50 / 1.000 posts"**.
- **Input schema (confirmado literalmente na aba Input):**
  - `username` (array) — descrito literalmente: *"Just insert a username or URL of the profile you want to get the user tagged posts from."*
  - `resultsLimit` (int) — *"Maximum number of user tagged posts you want to scrape per profile. If you set it to 5, you'll get 5 user tagged posts for each profile you've included."*
  - Fonte: `https://apify.com/apify/instagram-tagged-scraper/input-schema`.
- **Semântica confirmada:** o dataset retornado contém posts em que o(s) `username`(s) de input **aparecem como tag/menção feita por terceiros** — ou seja, o `ownerUsername`/`owner` de cada item do dataset é o autor do post (o seguidor/terceiro que gerou o UGC), não o perfil-alvo. Isso foi confirmado na aba API (exemplo de output real) e no texto da própria página: *"The scraper returns a dataset containing all posts where the specified username(s) appear as tags or mentions from other users."*
- **Output confirmado (exemplo JSON, aba API):** `id`, `type`, `shortCode`, `caption`, `hashtags`, `mentions` (array — contém o username do perfil-alvo, ex.: `"mentions": ["zelenskiy_official"]` no exemplo da própria página), `url`, `commentsCount`, `likesCount`, `timestamp`, `firstComment`, `latestComments` (com `ownerUsername`, `timestamp`, `likesCount` por comentário — amostra, não total).
- **Limitação declarada:** não há campo/flag na página que separe explicitamente "tagged in photo" (usertag visual) de "@mencionado na legenda" — o texto da própria Apify usa os dois termos ("tagged or mentions") de forma intercambiável, e o único exemplo mostrado é de menção em legenda/comentário, não de tag visual em foto. **Incerto** se o actor cobre ambos os mecanismos do Instagram (usertag em imagem vs. @mention em texto) ou só um deles — não confirmado por fonte primária além da descrição em prosa da página.

### 7.2 Alternativas community (para comparação/redundância)

#### `scraper-engine/instagram-tagged-and-mentions-posts-scraper` ("Instagram Tagged & Mentions Posts & Location Scraper")
- **URL:** https://apify.com/scraper-engine/instagram-tagged-and-mentions-posts-scraper
- **Dev:** Scraper Engine (community). 150 usuários totais, 6 mensais, 4.11/5 — adoção muito menor que o oficial (7.1).
- **Preço:** modelo diferente — **"$19.99/mês + taxas de uso"** (rental, não pay-per-event puro) — trade-off de custo fixo mensal vs. variável por resultado do actor oficial.
- **Input schema:** `usernameTargets` (array), `maxPostsPerAccount` (int, **10–1000**, faixa maior que o `resultsLimit` sem teto declarado do actor oficial), `maxCommentsPerPost` (int), `downloadMedia` (bool), `proxyConfig`.
- **Output confirmado:** `post_id`, `short_code`, `post_url`, `post_type`, `caption`, `like_count`, `comment_count`, `video_url`, `locationName`, `locationLat`/`locationLng`, `musicInfo`, `tagged_users`, `mentioned_user`, `hashtags`, `allMentions`, **`owner`** (dados do autor do post — confirma que é conteúdo de terceiros), `carouselMedia`, `is_paid_partnership`, `sponsor_user`, `scrapedAt`.
- **Confirmado explicitamente na página:** *"any post where that account was tagged or @-mentioned in a caption"* — mesma ambiguidade tag-visual-vs-menção-texto do actor oficial.
- Fonte: `https://apify.com/scraper-engine/instagram-tagged-and-mentions-posts-scraper`.

Outras variantes localizadas via busca mas **não abertas nesta pesquisa** (não confirmadas por fonte primária): `apify.com/scrapio/instagram-tagged-mentions-posts-scraper`, `apify.com/powerful_bachelor/instagram-tagged-mentions-posts-scraper`, `apify.com/instagram-scraper/instagram-tagged-posts-scraper`, `apify.com/seemuapps/instagram-tagged-posts-scraper` — listadas apenas como pistas.

### 7.3 O profile scraper atual (`shu8hvrXbJbY3Eb9W`) já suporta isso?

**Sim, parcialmente confirmado.** A página de input schema do actor genérico `apify/instagram-scraper` (que é o `shu8hvrXbJbY3Eb9W` já integrado ao pipeline — ver §0) lista `resultsType: "mentions"` como uma opção válida, descrita como retornando "posts where target profile is tagged". Fonte: `https://apify.com/apify/instagram-scraper/input-schema`. **Isso significa que, tecnicamente, o pipeline já tem acesso a esse dado sem adicionar um novo actor** — bastaria uma segunda chamada ao mesmo actor (`shu8hvrXbJbY3Eb9W`) com `resultsType: "mentions"` em vez de `"details"`. O schema de output exato para esse modo **não foi confirmado por exemplo JSON** nesta pesquisa (a página não renderizou um exemplo separado para `resultsType: mentions`) — presume-se, por ser o mesmo actor/código-base, que os campos sejam equivalentes aos de post (`caption`, `mentions`, `likesCount`, `commentsCount`, `ownerUsername`, `timestamp`), mas isso é **inferência, não confirmação direta**.

### 7.4 Hashtag scraper para UGC por hashtag de campanha

Reaproveitando §4.1 (`apify/instagram-hashtag-scraper`) e o modo `search`/`searchType: hashtag` do actor genérico (§1.3): ambos retornam posts de **quaisquer autores** que usaram uma hashtag específica (ex.: hashtag de campanha do governador), com `ownerUsername` (autor terceiro), `likesCount`, `commentsCount`, `reshareCount`, `caption`, `timestamp` — confirmado nos exemplos de output do §4.1. Isso cobre o caso "UGC por hashtag" mesmo quando o autor não usa `@menção` nem tag visual do perfil.

### 7.5 Como calcular "volume/engajamento de UGC" a partir desses actors

Nenhum dos actors pesquisados entrega a métrica agregada pronta ("volume de engajamento gerado por UGC no período X") — todos entregam **lista de posts individuais**, exigindo agregação do lado do pipeline. Para cada rota:

| Rota | Actor | Cálculo necessário no pipeline | Confiança da fonte |
|---|---|---|---|
| Tagged/mentioned posts (oficial) | `apify/instagram-tagged-scraper` | `COUNT(posts)` no período (filtrar por `timestamp`) para volume; `SUM(likesCount + commentsCount)` para engajamento agregado. Requer paginar via `resultsLimit` alto o suficiente para cobrir o período. | Alta — dados vêm diretamente da chamada, sem inferência |
| Tagged/mentioned posts (community, maxPostsPerAccount até 1000) | `scraper-engine/...` | Igual acima, usando `like_count + comment_count`; permite volume maior por execução (`maxPostsPerAccount` até 1000 vs. sem teto declarado no oficial, mas custo é assinatura mensal fixa | Média — página não é da Apify, dev community menor adoção |
| Hashtag de campanha | `apify/instagram-hashtag-scraper` ou `apify/instagram-scraper` com `search`/`searchType: hashtag` | Igual: `COUNT` + `SUM(likesCount + commentsCount + reshareCount)` filtrando por hashtag(s) de interesse | Alta para o primeiro (exemplo confirmado); média para o segundo (capacidade confirmada, schema de output não confirmado por exemplo) |
| Reconfigurar actor já integrado (`shu8hvrXbJbY3Eb9W`) para `resultsType: mentions` | `apify/instagram-scraper` (mesmo ID já em uso) | Igual à linha 1, mas **sem adicionar actor novo** — só mudar `run_input` no código existente | Média — capacidade confirmada, schema de output do modo `mentions` não confirmado por exemplo JSON primário |

**Trade-off de custo/complexidade resumido para esta frente:**
- **Menor esforço de integração:** reconfigurar o actor de perfil já em uso (`shu8hvrXbJbY3Eb9W`) para rodar também com `resultsType: "mentions"` — zero actors novos, mas schema de output não 100% confirmado nesta pesquisa (recomenda-se rodar um teste real antes de assumir os campos).
- **Maior confiabilidade/suporte:** `apify/instagram-tagged-scraper` — actor oficial, alta adoção (9.999 usuários), preço baixo ($1.50/1000), schema de output confirmado com exemplo real. Custo: um actor novo a integrar, e ambiguidade não resolvida sobre tag-visual vs. @menção.
- **Maior volume por execução:** `scraper-engine/instagram-tagged-and-mentions-posts-scraper` (`maxPostsPerAccount` até 1000) — mas custo fixo mensal ($19.99) + baixa adoção da comunidade (6 usuários/mês), risco de manutenção.
- **Cobertura de hashtag de campanha** (distinta de menção/tag): nenhum dos dois acima cobre isso — precisa do hashtag-scraper (§4.1) ou do modo `search` do actor genérico, como rota complementar, não substituta.

---

## 8. Síntese por nível COBRA

### Consuming (visualizar/curtir)
Já coberto razoavelmente pelo baseline: `likesCount`, `videoViewCount`, `videoPlayCount` já vêm de `apify/instagram-post-scraper` e `apify/instagram-reel-scraper` (confirmado, §1.1–1.2). Nenhum actor pesquisado entrega "watch time" real (tempo assistido, não apenas play count) — `videoPlayCount` é contagem de reproduções, não duração média assistida; **não encontrada** fonte primária de nenhum actor Apify que exponha watch-time real de vídeo (métrica que, no Instagram, só está disponível nativamente ao dono da conta via Meta Business Suite/Insights — fora do escopo de scraping público). Trade-off: para watch-time real, a única rota seria Instagram Graph API oficial com conta autenticada do governador, não um scraper de terceiros — fora do escopo desta pesquisa de actors Apify.

### Contributing (comentar/compartilhar/marcar/salvar)
- **Comentar:** parcialmente resolvido hoje via `latestComments` (amostra ~10). Actor dedicado `apify/instagram-comment-scraper` (§2.1) dá controle explícito de `resultsLimit` por post e replies/threads (`includeNestedComments`, paga) — mas não confirma capturar 100% do total de comentários de posts com muito volume.
- **Compartilhar:** `sharesCount` já disponível no actor de reels em uso (`apify/instagram-reel-scraper`) via flag `includeSharesCount` (plano Starter+) — **não é preciso trocar de actor**, só habilitar a flag e absorver custo do tier pago. `reshareCount` também confirmado no hashtag-scraper (§4.1) para reels retornados por hashtag.
- **Marcar (tag):** coberto pela linha "Mentions/Tagged posts" — ver §7 (mas aí o "marcar" é de terceiros marcando o perfil, o que tecnicamente já cruza para Creating/UGC; ver nota abaixo).
- **Salvar (saves):** **não encontrado** nenhum actor pesquisado que exponha contagem de "saves" — Instagram não expõe essa métrica publicamente para contas de terceiros (é só visível ao próprio dono no Insights nativo). Nenhuma fonte primária consultada contradiz isso.

### Creating (criar conteúdo/UGC sobre o perfil)
**Este é o nível com a lacuna mais concreta e mais opções mapeadas — ver §7 para o detalhamento completo.** Resumo:
- Existe actor oficial dedicado (`apify/instagram-tagged-scraper`) que retorna posts de terceiros que marcam/mencionam o perfil-alvo — dado mais direto disponível para "volume de UGC sobre o perfil".
- O actor de perfil já integrado ao pipeline (`shu8hvrXbJbY3Eb9W`) tecnicamente já suporta o mesmo tipo de busca (`resultsType: mentions`) sem precisar adicionar actor novo — capacidade não confirmada em detalhe de schema, mas confirmada em capacidade.
- Hashtag scraper (`apify/instagram-hashtag-scraper` ou modo `search` do actor genérico) cobre o caso complementar de UGC por hashtag de campanha (sem @menção/tag).
- Em nenhum caso o cálculo de "volume/engajamento agregado de UGC" vem pronto do actor — todos exigem agregação (`COUNT`, `SUM(likes+comments)`) do lado do pipeline sobre a lista de posts retornada.
- Trade-off central: reconfigurar o actor já em uso (mais barato, menos confirmado) vs. adicionar `apify/instagram-tagged-scraper` (mais confiável/documentado, custo incremental baixo — $1.50/1000 — e mais um actor para manter no `scraper.py`).

---

## 9. Lacunas e incertezas explícitas desta pesquisa

- Schema de output completo do modo `resultsType: "mentions"` do actor genérico (§7.3) **não foi confirmado** por exemplo JSON primário — apenas a capacidade de input foi confirmada.
- Não foi confirmado se `apify/instagram-tagged-scraper` distingue usertag visual de @menção em texto/comentário — ambos os actors pesquisados (oficial e community) usam os termos de forma intercambiável na documentação.
- Não foi possível confirmar limite máximo real de `resultsLimit` para comentários (§2.1) — a página não declara teto técnico.
- Actors de stories adicionais mencionados em buscas (`gordian/instagram-story-scraper`, `codenest/instagram-story-scraper`, `muhammetakkurtt/instagram-scraper`) **não foram abertos/confirmados** nesta pesquisa — citados apenas como pistas para investigação futura, não como achados.
- Preços listados são os publicados nas páginas dos actors em 2026-09-08 e podem mudar; todos são "a partir de" e variam por tier de assinatura Apify.
- Nenhum actor pesquisado expõe "saves" (salvamentos) — considerado indisponível via scraping de terceiros no Instagram atual, não apenas ausente destes actors específicos.

---

## Índice de fontes primárias citadas

- https://apify.com/apify/instagram-post-scraper (+ `/input-schema`, `/api`)
- https://apify.com/apify/instagram-reel-scraper (+ `/input-schema`)
- https://apify.com/apify/instagram-scraper (+ `/input-schema`)
- https://apify.com/apify/instagram-comment-scraper (+ `/input-schema`)
- https://apify.com/apify/instagram-profile-scraper
- https://apify.com/apify/instagram-hashtag-scraper
- https://apify.com/apify/instagram-tagged-scraper (+ `/input-schema`, `/api`)
- https://apify.com/scraper-engine/instagram-tagged-and-mentions-posts-scraper
- https://apify.com/afanasenko/instagram-follower-tracker
- https://apify.com/gordian/instagram-profile-history
- https://apify.com/automation-lab/instagram-stories-scraper
- https://apify.com/datavoyantlab/advanced-instagram-stories-scraper
- https://api.apify.com/v2/acts/shu8hvrXbJbY3Eb9W
- https://api.apify.com/v2/acts/apify~instagram-scraper
