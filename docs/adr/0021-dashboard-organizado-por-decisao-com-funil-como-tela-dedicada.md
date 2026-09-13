---
status: accepted
---

# Reformulação do dashboard de "por funil" para "por decisão", com o funil COBRA-RACE como tela dedicada (substitui a Frente 2 da ADR 0020)

## Contexto

A ADR [0020](0020-alinhamento-tcc-funil-cobra-race-nsm-ice-cmgr-e-reformulacao-do-dashboard-de-growth.md)
já entregou (issue #94, PR #105, merged) um dashboard de 5 páginas (`app.py` + `pages/01_explorar.py`
… `05_funil.py` + `src/dashboard/{loaders,filters,comparisons,recommendations}.py`) organizado por
**estágio do funil** RACE/COBRA — cada página cobre um recorte técnico (explorar, insights,
performance, recomendações, funil).

O usuário trouxe um documento externo (`ESPECIFICACAO_DASHBOARD.md`, Downloads, não versionado)
propondo reorganizar o dashboard por **decisão do analista de assessoria** ("como fechou a semana?",
"o que eu posto a seguir?", "tem algo pegando fogo?", "como estou vs. outros?", "estou falando do que
o público quer?"), com um princípio de design fixo por tela (frase de decisão em faixa semafórica →
KPIs com variação → prova) e uma lista de ressalvas de confiabilidade obrigatórias (NSM em validação,
CMGR ilustrativo, alcance sempre proxy, etc., já presentes no dicionário de dados do projeto).

Uma rodada de `/grilling` cruzando esse documento com o estado real do código (esta sessão) encontrou
cinco pontos de atrito que o documento por si só não resolvia:

1. O documento organiza por decisão, mas a ADR 0020 e o Cap. 6 do TCC têm o **funil COBRA-RACE como
   tese central de pesquisa** — sem uma tela dedicada ao funil, a ferramenta perderia a visibilidade
   dessa tese. Resolvido pelo próprio usuário durante o grilling, editando o documento para adotar uma
   estratégia híbrida (chamada "Opção C" no documento).
2. O esqueleto de acesso a dados do documento (`_repo.read("tabela")`) não corresponde à API real de
   `DeltaRepository`, que já expõe um método nomeado por tabela (`load_profiles` é o snapshot de
   `governor_engagement`; `load_comments` é a tabela `governor_sentiment` **sem** filtro de `fonte` —
   o filtro `fonte == 'comentario'` continua sendo responsabilidade de quem lê). Ajuste mecânico, não
   uma decisão de arquitetura.
3. Uma sessão anterior já validou uma separação de marca (vermelho/Inter da IESB só no "chrome" —
   navegação, títulos — nunca nos gráficos, que usam uma paleta `/dataviz` neutra à parte). O
   documento novo define sua própria paleta semafórica sem mencionar essa separação.
4. O documento usa linguagem de calendário ("semana", "últimos 7 dias", "4 semanas"), mas o pipeline
   não tem agendamento fixo hoje (execuções são manuais/ad hoc; o agendamento via lambda AWS é um item
   ainda pendente, ver `[[backfill_lambda_propagation_decision]]` em memória) — comparar "última
   execução vs. anterior" pode significar dias ou meses de intervalo, não uma semana real.
5. A tela do funil (Tela 6) usa `videoPlayCount` (visualizações reais, já existe em
   `governor_clusters`, nullable) para o estágio "Reach", enquanto NSM/Score ICE usam "alcance" como
   proxy de engajamento (curtidas+respostas) em todo o resto da ferramenta — dois números chamados
   "alcance"/"Reach" mas calculados de formas diferentes.

## Decisão

Substituir integralmente a Frente 2 (dashboard) da ADR 0020 — não a Frente 1 (pipeline/modelagem, que
continua válida e não é afetada). O dashboard atual (`app.py`, `pages/01-05_*.py`,
`src/dashboard/{loaders,filters,comparisons,recommendations}.py`, e os testes
`test_dashboard_loaders.py`/`test_comparisons.py`/`test_recommendations.py`/`test_charts.py`) é
**apagado**, não mantido em paralelo nem arquivado — substituído tela por tela, na ordem da
especificação, cada substituição já vindo com testes novos.

Estrutura nova: pacote `dashboard/` na raiz (`core/{data,theme,components,deltas}.py` +
`screens/{resumo,produzir,radar,comparar,discurso_reacao,funil}.py`), 6 telas (não 5 — o funil ganhou
tela própria, ver abaixo), navegação por `st.radio` em vez de multipágina nativa do Streamlit.

Resolução dos cinco pontos de atrito:

1. **Funil como Opção C (híbrida):** tela dedicada "Funil de engajamento" (Tela 6, carro-chefe) mais
   um rótulo discreto de estágio (`stage_label()`) no cabeçalho de cada uma das outras 5 telas,
   mapeando-a ao estágio RACE/COBRA correspondente. O funil deixa de ser uma entre cinco páginas
   organizadas por estágio e passa a ser uma lente que atravessa uma ferramenta organizada por
   decisão — a tese fica visível sem forçar a ferramenta inteira a ser lida como um funil.
2. **Acesso a dados:** `dashboard/core/data.py` chama os métodos já nomeados de `DeltaRepository`
   (`load_profiles`, `load_comments`, `load_nsm`, `load_growth_metrics`, `load_discourse_topics`,
   `load_topic_priority_score`, `load_profile_clusters_engagement`, `load_clusters`,
   `load_governors_metadata`, `load_engagement_history`, `load_sentiment_history`), cada um envolto em
   `@st.cache_data`. Nenhum método novo no repositório.
3. **Marca:** o "chrome" (navegação lateral, títulos de tela) mantém vermelho/Inter da IESB; a paleta
   semafórica do documento (verde/amarelo/vermelho/azul) é usada exatamente como especificada para
   faixa de decisão, KPIs e gráficos — ela já é, na prática, a paleta `/dataviz` desta reformulação,
   então a separação anterior continua valendo, só que agora com uma paleta de dataviz nova e
   documentada em `core/theme.py`.
4. **Linguagem de tempo:** "Resumo da semana" mantém o nome da tela (é a decisão que ela resolve, não
   uma promessa de cadência), mas toda comparação numérica troca "semana"/"7 dias" por linguagem de
   execução — "vs. última coleta", exibindo as datas reais das duas execuções comparadas — em vez de
   implicar uma cadência semanal que ainda não existe.
5. **Reach vs. alcance-proxy:** a Tela 6 rotula seu número de "Reach" como "Visualizações" (soma de
   `videoPlayCount`, um dado real), mantendo "alcance estimado por engajamento" como o rótulo/tooltip
   usado em NSM e Score ICE em todo o resto da ferramenta. Nenhuma tela usa a palavra "alcance" para
   os dois cálculos diferentes.

Processo de entrega: mesmo padrão das ADRs 0019/0020 — esta ADR primeiro, depois issues no GitHub
(`ready-for-agent`), uma por unidade (Fundamentos + 6 telas, na ordem da Parte 3 da especificação:
Fundamentos → Resumo → O que produzir → Radar → Funil → Comparar → Discurso×Reação), cada uma via TDD
e `/code-review` Standards+Spec antes do merge. `/to-spec` não está instalado neste ambiente (checado
nesta sessão) — as issues são escritas à mão espelhando o formato da issue #50, como já registrado em
memória. Conteúdo curado incorporado ao código (nomes dos grupos de perfil na Tela 4, mapa de
taxonomia comum de tópicos na Tela 5) é proposto e documentado pelo agente implementador, mas revisado
por Claude antes do merge — sempre via PR, nunca merge direto na `main`, dado que a ferramenta
influencia decisões reais de comunicação política (Parte 4 da especificação).

Esta ADR **substitui a Frente 2 da ADR 0020** (a seção de dashboard); a Frente 1 (pipeline/modelagem —
clusterização de perfil e de feed, sentimento de legenda/transcrição, tópicos de discurso, NSM, Score
ICE, CMGR, UGC) permanece válida e inalterada, incluindo as tabelas Gold que ela introduziu — esta ADR
só reorganiza como essas tabelas são apresentadas.

## Por que

- Organizar por decisão (não por técnica/estágio) é o pedido explícito do usuário e o critério de
  qualidade que o próprio documento define ("abra a tela e pergunte 'e agora, o que eu faço?'") — o
  dashboard anterior (ADR 0020) já expunha as métricas certas, mas exigia que o analista soubesse
  antecipadamente qual página técnica olhar para responder uma pergunta de growth.
- O funil vira tela dedicada + rótulo transversal, em vez de uma das cinco páginas, porque nenhuma das
  duas opções extremas (só uma aba isolada vs. reorganizar tudo em torno do funil) atendia às duas
  exigências simultâneas: a ferramenta precisa ser usável por decisão *e* a tese COBRA-RACE do TCC
  precisa ficar explícita em mais de um lugar.
- Apagar o dashboard antigo em vez de mantê-lo em paralelo: o público-alvo é o mesmo (analista de
  assessoria) e as duas organizações competiriam pela mesma atenção sem ganho — manter as duas até o
  fim só adiaria o trabalho de decidir qual fica.
- `core/data.py` reaproveita os métodos já nomeados de `DeltaRepository` em vez do `_repo.read(tabela)`
  do documento original porque esse método genérico não existe e criar um introduziria uma segunda
  forma de acessar as mesmas tabelas, sem necessidade.
- Reach real (`videoPlayCount`) na Tela 6 em vez do proxy de engajamento usado em NSM/ICE: dado que a
  Tela 6 tem esse dado real disponível por reel, descartá-lo em favor de um proxy pioraria a
  informação sem necessidade — o problema era só o nome ambíguo, resolvido rotulando os dois
  diferentemente.
- Revisão do conteúdo curado (Telas 4 e 5) antes do merge, mas sempre via PR: mesma decisão do usuário
  desta sessão, coerente com o alerta de honestidade analítica que o próprio documento carrega (Parte
  4) — nomes de grupo e mapas de tópico são julgamento subjetivo embutido em uma ferramenta que
  influencia comunicação política real.

## Opções consideradas

- **Manter `pages/05_funil.py` como uma sexta página ao lado das cinco novas telas**, sem mexer na
  organização geral — rejeitada durante o grilling: duplicaria a apresentação de várias métricas
  (funil e "Resumo da semana" cobrem parte do mesmo território) sem ganho de clareza.
- **Diluir os estágios RACE dentro de "Resumo da semana"**, sem tela dedicada — rejeitada: a tese do
  TCC ficaria implícita demais para servir de prova no Cap. 6.
- **Manter o dashboard antigo rodando até as 6 telas novas estarem prontas**, cutover só numa PR final
  de limpeza — rejeitada pelo usuário em favor de apagar e substituir tela por tela, evitando código
  mantido em paralelo por um período longo.
- **Abandonar a marca IESB em favor da paleta genérica do documento** — rejeitada: descartaria o
  trabalho já validado de separação marca/dataviz sem necessidade, já que a paleta semafórica do
  documento se encaixa perfeitamente no papel de paleta `/dataviz`.
- **Usar o mesmo cálculo de alcance-proxy também na Tela 6**, por consistência de fórmula — rejeitada:
  jogaria fora um dado real (`videoPlayCount`) só para manter uma palavra idêntica em todo lugar; a
  solução de rotular diferente resolve a ambiguidade sem perder informação.

## Consequências

- `app.py`, `pages/01_explorar.py` … `05_funil.py`, `src/dashboard/{loaders,filters,comparisons,recommendations}.py`
  e os testes `test_dashboard_loaders.py`/`test_comparisons.py`/`test_recommendations.py`/`test_charts.py`
  são removidos incrementalmente à medida que cada tela nova entra — nenhuma issue está "completa" sem
  também remover o código/teste antigo que ela substitui.
- A ADR 0020 recebe uma nota curta no topo apontando para esta ADR — quem ler 0020 sozinha precisa
  saber que a Frente 2 (dashboard) não reflete mais o estado atual.
- O selo "engajamento qualificado" (NSM), os selos "em validação"/"ilustrativo"/"experimental" e o
  rodapé "Análise baseada em comentários de Reels" — todos já obrigatórios pelo dicionário de dados —
  precisam sobreviver à reescrita; cada issue de tela deve conferir o checklist da Parte 3 da
  especificação antes de considerar a tela pronta.
- `governor_clusters.videoPlayCount` é nullable — a soma para "Visualizações" na Tela 6 precisa tratar
  reels sem esse dado (`NaN`/ausente) sem quebrar nem subestimar silenciosamente o total.
- Nenhuma tabela `ugc_*` é lida por nenhuma tela nova (mesma restrição já registrada no dicionário de
  dados) — o estágio "Engage/Criar" da Tela 6 permanece "em construção" até a Ficha 8 da ADR 0020
  entregar dado real de produção (ver nota já registrada na ADR 0020 sobre `governor_ugc_mentions` ter
  zero linhas reais hoje).
