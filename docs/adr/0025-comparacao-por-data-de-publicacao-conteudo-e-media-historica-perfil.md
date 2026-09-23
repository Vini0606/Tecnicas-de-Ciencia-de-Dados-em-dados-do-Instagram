---
status: accepted
---

# Comparação temporal por data de publicação (conteúdo) e por média histórica (perfil), abandonando execução-a-execução

## Contexto

O usuário pediu uma sessão de `/grill-with-docs` para revisar 3 mudanças no dashboard vindas do handoff de
2026-09-23: indicador de média nos KPIs do Resumo (Tela 1), mover a "Evidência histórica de desempenho" de
volta pro Resumo (reabrindo a ADR [0024](0024-substituir-grafico-por-coleta-do-resumo-por-evidencia-de-desempenho-por-publicacao-em-o-que-produzir.md)),
e remover a seção "Destaques da execução" do Resumo -- ver ADR [0026](0026-resumo-perde-destaques-ganha-evidencia-e-kpis-de-crescimento-redistribuicao-produzir-radar.md)
(companion desta) para a reorganização de tela resultante desses dois últimos itens.

Ao grelhar o indicador de média (item 1), o usuário declarou um objetivo mais amplo que o pedido original:
**substituir toda lógica de análise "por coleta" por "por data de publicação", para não precisar rodar
coletas com cadência apertada/diária**. Isso é uma extensão direta do ponto de atrito 4 já registrado pela
ADR [0021](0021-dashboard-organizado-por-decisao-com-funil-como-tela-dedicada.md): a pipeline não tem
cadência fixa (execuções são manuais/ad hoc), então "última execução vs. anterior" pode significar um
intervalo de dias ou meses, não uma semana real -- a ADR 0021 só mitigou isso trocando o RÓTULO ("vs. última
coleta", com datas reais visíveis); nunca removeu a comparação execução-a-execução em si.

Levantamento contra o código real (nesta sessão) confirmou que a meta do usuário é alcançável para parte do
dado, mas não para todo ele:

- **Métricas de conteúdo** (curtidas, comentários, visualizações, % positivo/negativo de comentários) --
  cada linha (`reels_clean`/`posts_clean`/`governor_sentiment_history`) tem um timestamp real de publicação.
  As ADRs [0023](0023-filtro-de-calendario-por-data-de-publicacao-no-radar-e-resumo.md) e 0024 já haviam
  migrado PARTE dessas métricas (linha do tempo do Radar; evidência de "O que produzir") para data de
  publicação -- mas o critério PRINCIPAL de alerta do Radar (`radar.py::_tema_maior_alta_negatividade`,
  `_nivel_semaforo`) e o `% positivo` do Resumo continuavam comparando execução-a-execução
  (`core.deltas.week_over_week`, `_run_id`).
- **Métricas de perfil** (`Seguidores`, `% engajamento` de `governor_engagement`, NSM) -- são rollups
  calculados NO MOMENTO da coleta (ex.: quantos seguidores o perfil tinha quando rodamos a coleta). Não
  existe "data de publicação" para um número de seguidores; não tem como reformular isso sem inventar um
  dado que não existe.

## Decisão

**Métricas de conteúdo** passam a comparar por **janela de data de publicação**, nunca mais por execução:

- Radar (Tela 3): o critério PRINCIPAL de alerta muda de "delta entre as 2 execuções mais recentes" para
  "últimos N dias de publicação vs. os N dias anteriores" (`_tema_maior_alta_negatividade` e a parte "warn"
  de `_nivel_semaforo` são redesenhados). O corte "danger" (`pct_negativo_atual >= limiar`) **não muda** --
  já era um corte absoluto, sem comparação nenhuma.
- Resumo (Tela 1): `% positivo` passa a usar a mesma lógica de janela por data de publicação do comentário,
  em vez de `_agregar_pct_positivo_por_run` + `week_over_week` por `_run_id`.
- `N` = `JANELA_ALERTA_NEGATIVIDADE_DIAS`, nova constante, **default 7** -- mesmo valor já usado em dois
  outros lugares do dashboard (`_JANELA_DESTAQUE_PUBLICACOES_DIAS`, quebra de linha de gráfico em gap > 7
  dias) -- **configurável via `.env`**. Self-contained em `dashboard/core/deltas.py` (ganha seu próprio
  `load_dotenv()` -- primeira vez que o dashboard lê `.env`), **não** em `config/settings.py`: o dashboard
  nunca importou nada de outro pacote do projeto, e a ADR 0021 já estabeleceu essa autocontenção como
  princípio para as telas novas.

**Métricas de perfil** não têm data de publicação -- continuam comparando entre execuções, mas trocam
"vs. última execução" (delta de 1 passo, `week_over_week`) por **"vs. média histórica de todas as
execuções disponíveis"** -- resiliente a qualquer espaçamento real entre coletas (1 dia ou 3 meses, tanto
faz):

- `% engajamento`, `Seguidores` (`governor_engagement`, já tem histórico via `load_engagement_history()`).
- NSM (`Engajamento qualificado`) -- exige `load_nsm_history()` novo em `dashboard/core/data.py` (hoje só
  existe `load_nsm()`, snapshot). Forma exata de implementação (a tabela Gold `governor_nsm` já grava
  `_run_id`/`_generated_at` por linha; se o modo de escrita real acumula histórico ou sobrescreve é uma
  pergunta de implementação, não resolvida no grilling) fica para `/to-spec`/`/implement`.

**A regra de combinação da frase de decisão do Resumo não muda** -- `_nivel_semaforo` continua "good" se os
dois deltas (agora de fontes diferentes) forem favoráveis, "warn" se algum for desfavorável, "danger" se a
negatividade cruzar o limiar. Só a FONTE dos dois deltas muda, não a regra de decisão.

## Por que

- Objetivo explícito do usuário: não depender de rodar coletas em cadência apertada pra ter comparações
  temporais significativas -- resolve de vez o ponto de atrito 4 da ADR 0021, que antes só havia sido
  mitigado no texto/rótulo, não na lógica.
- A separação conteúdo/perfil não é estética -- é um limite real de dado, confirmado no código antes de
  desenhar a solução (mesmo cuidado já registrado na ADR 0024): inventar uma "data de publicação" para
  seguidores ou NSM produziria um número sem significado.
- Generaliza um padrão já parcialmente adotado (ADR 0023/0024) para o resto do dashboard, em vez de um
  terceiro critério temporal diferente.
- Janela de 7 dias reaproveita uma constante que já é convenção no código, em vez de inventar um novo
  número arbitrário.
- Constante self-contained em `dashboard/core/deltas.py` (não em `config/settings.py`): preserva a
  autocontenção de pacote que a ADR 0021 já fixou para o dashboard novo -- seria a primeira dependência
  cruzada entre o dashboard e outro pacote do projeto.

## Opções consideradas

- **Eliminar toda comparação temporal (só valores absolutos, sem nenhum delta)** -- rejeitada: perderia a
  frase de decisão e o alerta de tendência que dão sentido às Telas 1 e 3; o usuário nunca pediu isso, só
  não queria depender de cadência de coleta apertada.
- **Aplicar "média histórica" também às métricas de conteúdo**, em vez de janela por data de publicação --
  rejeitada: descartaria a granularidade de data real já disponível por post/comentário, que é exatamente o
  que a ADR 0023/0024 provaram funcionar bem.
- **Guardar `JANELA_ALERTA_NEGATIVIDADE_DIAS` em `config/settings.py`** (módulo de settings já existente,
  usado por `pipeline.py`) -- rejeitada: seria a primeira dependência do dashboard em outro pacote do
  projeto, contrariando a autocontenção que a ADR 0021 já fixou.

## Consequências

- `dashboard/core/deltas.py`: ganha `JANELA_ALERTA_NEGATIVIDADE_DIAS` (default 7, via `.env`) e
  `load_dotenv()`; `week_over_week` deixa de ser chamado pelo critério principal do Radar e por
  `% positivo`/`% engajamento`/`Seguidores` do Resumo -- precisa de função(ões) nova(s) para "janela por
  data de publicação" e para "vs. média histórica de execuções".
- `dashboard/screens/radar.py`: `_tema_maior_alta_negatividade` e a parte "warn" de `_nivel_semaforo`
  redesenhadas para a janela de 7 dias por data de publicação.
- `dashboard/screens/resumo.py`: `_delta_para_governador`/`_agregar_pct_positivo_por_run` substituídos --
  `% positivo` usa a nova lógica de janela; `% engajamento`/`Seguidores`/NSM usam a nova lógica de "vs.
  média histórica".
- `dashboard/core/data.py`: ganha `load_nsm_history()`.
- `.env.example` ganha `JANELA_ALERTA_NEGATIVIDADE_DIAS=7`.
- `tests/test_dashboard_core_deltas.py`, `tests/test_dashboard_screens_radar.py`,
  `tests/test_dashboard_screens_resumo.py` precisam de casos novos para os dois critérios (janela por
  publicação; vs. média histórica).
- Issue #149 (`ready-for-human`, `sharesCount`) e o backfill de 5 dias pendente (ver handoffs anteriores)
  não têm relação de dependência com esta ADR.
