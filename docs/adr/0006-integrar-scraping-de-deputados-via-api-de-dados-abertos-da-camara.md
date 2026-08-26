---
status: accepted
---

# Integrar scraping de deputados via API de dados abertos da Câmara, com roster próprio em Bronze e metadados unificados no Silver

## Contexto

O ADR [0004](0004-manter-pipelines-separados-por-entidade-sem-generalizar-schema-agora.md) decidiu que uma segunda entidade política (deputados) rodaria em datasets completamente separados dos governadores, mas deixou deliberadamente em aberto o schema do roster de entrada, onde os metadados de entidade (partido, estado, cargo) entram no Medallion, como o processo de coleta existente do usuário mapeia para a arquitetura atual, e a nomenclatura das tabelas Gold. Esta sessão é onde essa decisão vira prática — a primeira implementação real da frente multi-entidade.

O usuário tinha um projeto próprio, fora deste repositório, em `C:\VHL Comunicações\repositorio\projeto-deputados`, usado na última coleta de dados de deputados. Investigação desse projeto mostrou que ele:

- Faz scraping via Selenium da página HTML `camara.leg.br/deputados/quem-sao`.
- Coleta apenas metadados institucionais: Nome Civil, Partido (formato `"SIGLA - UF"`), E-mail, Telefone, Endereço do gabinete, Data de Nascimento, Naturalidade — sem nenhum link ou handle de Instagram.
- Produziu um `deputados.xlsx` (511 linhas) com mojibake de encoding nas colunas acentuadas (`Endere�o`, `Naturalidade`) — o mesmo problema já presente em `data/raw/governadores.xlsx`.
- Tem um notebook auxiliar (`scraping_emails.ipynb`) vazio (0 bytes), sem uso.

Ou seja: **o processo de coleta existente do usuário não é uma fonte de dados de Instagram** — ele resolve só a parte de metadados institucionais, e nem essa parte de forma ideal (HTML scraping frágil, sem link de rede social, com bug de encoding recorrente). Sem um link de Instagram por deputado, o pipeline de engajamento/sentimento (que depende de `InstagramScraper.scrape_profiles(links)`, ver `src/data_extract/scraper.py:28`) não tem o que processar — esse era o gap real a resolver, não previsto no ADR 0004.

Durante o `/grilling`, testamos ao vivo a API de dados abertos da Câmara (`dadosabertos.camara.leg.br/api/v2`):

- `GET /deputados` retorna a lista paginada com `id`, `nome`, `siglaPartido`, `siglaUf`, `idLegislatura`, `email` — já cobre a maior parte do roster.
- `GET /deputados/{id}` retorna o perfil completo, incluindo `redeSocial` (array de URLs de redes sociais auto-declaradas pelo parlamentar). Testado em 3 deputados: 2 tinham link de Instagram no array (`instagram.com/usuario`), 1 não tinha (só Twitter/Facebook/YouTube) — confirma que a cobertura não é de 100% dos deputados, mas a fonte é estruturada, oficial e sem parsing de HTML.

## Decisão

1. **Fonte de dados**: abandonar o Selenium do `projeto-deputados` como fonte de coleta. Usar a API `dadosabertos.camara.leg.br/api/v2` (`/deputados` para o roster + `/deputados/{id}` para `redeSocial`) como fonte única de roster e de link de Instagram. Deputados sem `redeSocial` contendo `instagram.com` ficam sem link de Instagram — não entram no scraping do Instagram, mas continuam no roster (ver ponto 7).
2. **Persistência do roster**: gravar o roster como tabela Delta em Bronze (`data/bronze/deputy_roster`), não como planilha `.xlsx`. Evita reintroduzir o bug de mojibake e reaproveita a infraestrutura `deltalake` já usada pelo pipeline de Instagram.
3. **Onde os metadados entram no Medallion**: a etapa Silver do pipeline de deputados faz o join do roster (Bronze) com o profile do Instagram raspado, por username extraído do link — resultando em colunas `partido`/`uf`/`legislatura` diretamente em `profiles_clean`. Gold e dashboards herdam esses campos sem precisar repetir o join.
4. **Onde vive o código de coleta**: novo módulo dedicado `src/data_extract/camara_client.py`, com uma classe (ex.: `CamaraDeputadosClient`) responsável só por falar com a API da Câmara, e um schema próprio em `schemas_delta.py` (`BRONZE_DEPUTY_ROSTER_SCHEMA`). O `BronzeWriter` existente não é generalizado — continua exclusivo do pipeline Instagram/Apify (schemas fixos, `_source="apify"`).
5. **Nomenclatura**: manter o padrão em inglês já usado por `governor_*`. Tabelas Gold de deputados: `deputy_engagement`, `deputy_sentiment`, `deputy_clusters`. Roster em Bronze: `deputy_roster`.
6. **Como o pipeline escolhe a entidade**: `run_medallion_pipeline()` é parametrizado para receber os caminhos Bronze/Silver/Gold (e um passo opcional de join de roster) em vez de usar `settings.GOLD_ENGAGEMENT` etc. hardcoded internamente — mantendo os defaults de governador. Um novo `scripts/run_pipeline_deputados.py` monta os parâmetros de deputado e chama a mesma função, em vez de duplicar a orquestração Bronze→Silver→Gold. `DeltaRepository` ganha um parâmetro de entidade no construtor.
7. **Cobertura sem Instagram**: `deputy_roster` guarda todos os ~513 deputados, com o link de Instagram nulo para quem não tem. O join no Silver `profiles_clean` é um inner join — só quem foi de fato raspado aparece nas tabelas de engajamento/sentimento/clusters. A cobertura (quantos % têm Instagram cadastrado) pode ser calculada consultando o roster completo, sem poluir as tabelas de análise com registros vazios.
8. **Frequência de atualização / rate limit**: o refresh do roster (as ~513 chamadas individuais a `/deputados/{id}`) roda como script próprio (`scripts/refresh_deputados_roster.py`), desacoplado do pipeline de scraping do Instagram, chamado periodicamente (não a cada execução). Chamadas sequenciais com um pequeno intervalo entre elas (educação com uma API pública sem limite de rate documentado). O pipeline de Instagram sempre lê o último snapshot já salvo em `deputy_roster`, nunca chama a API da Câmara diretamente.

**Nenhuma mudança de código acontece nesta sessão** — este ADR só registra o desenho acordado. A implementação (novo `camara_client.py`, schemas, scripts, parametrização de `pipeline.py`/`DeltaRepository`) fica para uma sessão futura.

## Por que

- O gap real (ausência de fonte de Instagram) só apareceu ao investigar o código do `projeto-deputados` de perto — o handoff anterior assumia que esse projeto já resolvia a coleta, o que não era o caso. Vale registrar isso explicitamente para não repetir a suposição.
- A API de dados abertos é oficial, estruturada e testada ao vivo nesta sessão — elimina de uma vez o parsing de HTML frágil e o bug de encoding que já apareceu duas vezes no projeto (`governadores.xlsx` e `deputados.xlsx`).
- Persistir o roster como Delta em Bronze, em vez de `.xlsx`, evita reintroduzir esse mesmo bug e trata a coleta de deputados como ingestão normal do Medallion, não como um arquivo de configuração editado à mão — papel que fazia sentido para `governadores.xlsx` (curado manualmente) mas não para um roster obtido por API.
- Denormalizar partido/UF/legislatura em `profiles_clean` (em vez de manter só uma dimensão separada) evita repetir lógica de join em cada consumidor (`EngagementAggregator`, dashboards) — o profiles_clean já é a granularidade "uma linha por perfil" que tanto Gold quanto dashboard leem hoje.
- Um módulo novo (`camara_client.py`) em vez de generalizar `BronzeWriter` evita acoplar duas fontes de dados (Apify/Instagram vs. API institucional da Câmara) numa classe pensada para uma só, seguindo o mesmo espírito de "não generalizar sem caso real" do ADR 0004.
- Parametrizar `run_medallion_pipeline()` em vez de duplicar o pipeline inteiro evita repetir a orquestração Bronze→Silver→Gold, que é idêntica entre entidades — só os caminhos e um passo de join mudam.
- Desacoplar o refresh do roster do pipeline principal evita pagar ~513 chamadas HTTP a cada execução de scraping do Instagram, para um dado (partido, redes sociais) que raramente muda de um dia para o outro.

## Opções consideradas

- **Estender o Selenium existente do `projeto-deputados` para também capturar redes sociais** — rejeitada: mantém o parsing de HTML frágil e o risco de mojibake; a API oficial já resolve o mesmo problema de forma mais robusta.
- **Buscar Instagram por fonte externa/curadoria manual** — rejeitada por ora: a API cobre a maioria dos casos testados sem esforço manual; curadoria manual para ~513 deputados não escala.
- **Manter roster em `.xlsx`/`.csv` em `data/raw/`, no mesmo padrão de `governadores.xlsx`** — rejeitada: `.xlsx` já causou bug de encoding duas vezes; e diferente do roster de governadores (curado à mão), o de deputados é obtido por API, não há razão para o intermediário de planilha.
- **Roster como tabela de dimensão separada, com join só no Gold/dashboard** — rejeitada: mais "normalizado" no papel, mas replica a lógica de join em múltiplos consumidores; `profiles_clean` já é o ponto único por onde Gold e dashboard passam.
- **Generalizar `BronzeWriter` para aceitar uma quarta entidade (roster)** — rejeitada: mistura duas fontes de dados diferentes (Apify/Instagram vs. API da Câmara) numa classe hoje coesa em torno de uma só.
- **Nomear tabelas como `deputado_*` em vez de `deputy_*`** — rejeitada: quebraria o paralelismo com `governor_*`, único padrão de nomenclatura de tabela já estabelecido no código.
- **Pipeline totalmente separado (`pipeline_deputados.py` como cópia independente)** — rejeitada: duplicaria a orquestração Bronze→Silver→Gold, que não muda por entidade.
- **Excluir deputados sem Instagram completamente do roster** — rejeitada: perde a visibilidade de cobertura (quantos/quais deputados não têm presença), informação potencialmente relevante para a análise.
- **Buscar o roster da API a cada execução do pipeline de Instagram** — rejeitada: paga a latência de ~513 chamadas HTTP repetidamente por um dado que raramente muda.

## Consequências

- O `projeto-deputados` (Selenium) fica obsoleto para este propósito — não será integrado ao repositório; a API de dados abertos o substitui inteiramente.
- Nenhum código foi escrito nesta sessão. A implementação completa (`camara_client.py`, `BRONZE_DEPUTY_ROSTER_SCHEMA`, join de roster no `ProfileCleaner`, parametrização de `run_medallion_pipeline()` e `DeltaRepository`, `scripts/refresh_deputados_roster.py`, `scripts/run_pipeline_deputados.py`) continua pendente para uma sessão futura de implementação.
- A cobertura de Instagram entre deputados não é garantida — parte dos ~513 deputados não terá dados de engajamento/sentimento/clusters simplesmente por não ter cadastrado Instagram na Câmara. Isso deve ser comunicado como limitação conhecida ao apresentar qualquer análise.
- O roster de deputados passa a depender de disponibilidade externa (API da Câmara) no momento do refresh — diferente do roster de governadores, que é um arquivo estático mantido manualmente. Uma falha ou mudança de contrato da API afeta só o refresh do roster, não o pipeline de scraping do Instagram em si (que lê o snapshot já salvo).
- `run_medallion_pipeline()` e `DeltaRepository` passam a ter uma superfície de parâmetros maior (caminhos por entidade) — qualquer mudança futura nesses dois pontos precisa considerar as duas entidades.
