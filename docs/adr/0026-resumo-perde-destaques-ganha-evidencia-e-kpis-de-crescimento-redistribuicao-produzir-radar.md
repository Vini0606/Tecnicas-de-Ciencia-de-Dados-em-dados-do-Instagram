---
status: accepted
---

# Resumo perde os destaques narrativos, ganha a evidência histórica e 2 KPIs de crescimento; destaques redistribuídos para Produzir e Radar

## Contexto

O handoff de 2026-09-23 pedia reconsiderar 3 mudanças no Resumo (Tela 1): indicador de média nos KPIs,
mover a "Evidência histórica de desempenho" (ADR [0024](0024-substituir-grafico-por-coleta-do-resumo-por-evidencia-de-desempenho-por-publicacao-em-o-que-produzir.md))
de volta pro Resumo, e remover a seção "Destaques da execução". Sessão de `/grill-with-docs` (esta) tratou
os dois últimos itens como uma decisão só, porque a "prova" da estrutura fixa da ADR
[0021](0021-dashboard-organizado-por-decisao-com-funil-como-tela-dedicada.md) (cabeçalho -> frase de decisão
-> KPIs -> prova) pode ser preenchida tanto pelos destaques narrativos quanto pelo gráfico de evidência --
não pelos dois ao mesmo tempo sem inchar a tela.

Levantamento contra o código (`dashboard/screens/resumo.py`, `radar.py`, `produzir.py`, nesta sessão)
encontrou que dos 4 "Destaques da execução" atuais, só 2 são informação exclusiva do produto:

- **Melhor post** (`_melhor_post`) -- único, não aparece em nenhuma outra tela.
- **Tema em alta de negatividade** (`_maior_alta_negatividade`) -- **redundante** com o Radar
  (`radar.py::_tema_maior_alta_negatividade`), que já tem uma versão própria -- mas com um CRITÉRIO
  diferente (Resumo: maior % negativo NUM PERÍODO escolhido; Radar: maior VARIAÇÃO entre 2 execuções) --
  são perguntas diferentes, não a mesma métrica com nomes parecidos.
- **Alto potencial, pouco discurso** (`_topico_alto_positivo_baixo_discurso`) -- único, não aparece em
  nenhuma outra tela; a própria legenda já apontava "Ver mais em O que produzir (em construção)", nunca
  construído lá.
- **Publicações recentes** (`_contagem_publicacoes_recentes`) -- **superado**: o gráfico de evidência que
  está migrando pra cá já tem "quantidade de publicações" como métrica selecionável.

A ADR [0025](0025-comparacao-por-data-de-publicacao-conteudo-e-media-historica-perfil.md) (companion desta,
nascida na mesma sessão a partir do item do indicador de média) redesenha o critério PRINCIPAL de alerta do
Radar para também usar data de publicação -- o que evita que a "segunda leitura" migrada aqui fique
redundante com o critério principal redesenhado (ver "Decisão" abaixo).

## Decisão

**Tela 1 (Resumo):**
- Remove a seção "Destaques da execução" inteira (4 cartões) -- sem substituto direto na mesma forma.
- Cabeçalho volta a ter só o seletor de governador (sem segunda coluna) -- o filtro de calendário de
  negatividade que vivia ali sai junto com o destaque que ele alimentava.
- O gráfico "Evidência histórica de desempenho" (seletor Tipo de conteúdo x Métrica x Período, ADR 0024)
  migra INTEIRO de "O que produzir" para cá, com seu próprio filtro de calendário embutido na seção (não
  promovido ao cabeçalho -- ADR 0024 já era explícita que esse filtro é próprio da seção, não da tela) --
  essa seção passa a ser a "prova" da tela, no lugar dos destaques.
- Ganha 2 KPIs novos, numa segunda linha de `kpi_row()` chamada "Crescimento": **CMGR** e **retenção de
  sentimento positivo** (`governor_growth_metrics`, já carregável via `data.load_growth_metrics()`), cada
  um com seu selo de confiabilidade (`cmgr_confiavel`/`retencao_confiavel`/`ilustrativo`/`cmgr_motivo`/
  `retencao_motivo`) -- **sem** indicador de comparação (nem "vs. última execução", nem "vs. média
  histórica"): são taxas de tendência; comparar uma taxa contra sua própria média seria uma comparação de
  segunda ordem, mais confusa que útil.
- Os 4 KPIs existentes (NSM, % engajamento, % positivo, Seguidores) permanecem na primeira linha e ganham o
  indicador de comparação -- fonte exata de cada delta é definida pela ADR 0025 (companion desta).

**Tela 2 (O que produzir):**
- Não recebe mais nenhuma cópia do gráfico de evidência -- só um link "Ver evidência completa no Resumo",
  no lugar onde a seção existia (logo depois de "Formatos de Reel").
- Ganha uma seção nova "Destaques" (2 cartões, não 4), na MESMA posição que a evidência deixou: "Melhor
  post" e "Alto potencial, pouco discurso", com as funções puras portadas de `resumo.py` sem mudança de
  critério.

**Tela 3 (Radar de crise):**
- Ganha uma segunda leitura, logo abaixo da linha do tempo existente, **reaproveitando o mesmo filtro de
  calendário já ali** (não um filtro novo): "tema mais negativo no período selecionado" -- portado do
  destaque "Tema em alta de negatividade" do Resumo, sem mudar seu critério (maior % negativo agregado no
  intervalo escolhido).
- Essa segunda leitura continua distinta do critério PRINCIPAL do Radar mesmo depois da ADR 0025 redesenhar
  esse critério para janela fixa de 7 dias por data de publicação: a leitura principal usa uma janela
  AUTOMÁTICA e fixa (7 dias vs. 7 dias anteriores), enquanto a segunda leitura usa um período LIVRE,
  escolhido pelo analista -- perguntas complementares (alerta automático vs. exploração dirigida), não a
  mesma coisa duas vezes.

## Por que

- Tratar "mover a evidência" e "remover os destaques" como uma decisão só evita a contradição aparente com
  o princípio fixo da ADR 0021 (decisão -> KPIs -> prova): a prova muda de FORMA (de 4 cartões narrativos
  para 1 gráfico interativo), não desaparece.
- Só realoca (nunca descarta) as 2 informações exclusivas do produto (melhor post; alto potencial/pouco
  discurso) -- descartá-las seria perda real de informação, não simplificação; ambas encaixam melhor em "O
  que produzir" (pergunta de conteúdo) do que no Resumo (pergunta de "como foi minha semana").
- Não duplica a implementação do gráfico de evidência em 2 telas -- custo de manutenção de um seletor com
  estado próprio em dois lugares, sem benefício claro sobre um link de volta.
- "Tema em alta de negatividade" muda de tela (Resumo -> Radar) em vez de ser descartado, porque é uma
  pergunta de crise/monitoramento, não uma pergunta de "o que produzir" -- é uma correção de lugar, não uma
  remoção de funcionalidade; o Radar é literalmente a tela dedicada a essa decisão.
- CMGR/retenção entram sem indicador de comparação: já são métricas de variação; empilhar mais uma
  comparação em cima adicionaria confusão sem necessidade clara, além de exigir outro accessor de histórico
  novo (`load_growth_metrics_history()`) sem caso de uso comprovado ainda.

## Opções consideradas

- **Manter cópia do gráfico de evidência em ambas as telas** -- rejeitada: duplicação de manutenção de
  estado/seletor sem ganho sobre um link cruzado (mesmo padrão já usado 2x no dashboard).
- **Descartar "melhor post" e "alto potencial/pouco discurso" de vez, sem realocar** -- rejeitada: perda
  real de informação do produto, sem necessidade -- o usuário preferiu realocar quando confrontado com essa
  distinção.
- **Trazer o critério do Resumo para o Radar SUBSTITUINDO (não somando) o critério principal existente** --
  rejeitada: são perguntas diferentes (tendência automática recente vs. concentração num período livre);
  melhor manter as duas leituras lado a lado.
- **Promover o filtro de calendário do gráfico de evidência para o cabeçalho do Resumo**, já que a coluna
  ficaria livre -- rejeitada: nunca foi pensado como filtro global da tela (ADR 0024 já era explícita
  nisso); o cabeçalho volta a ter só o seletor de governador.
- **Indicador de "vs. média histórica" também em CMGR/retenção** -- rejeitada: comparação de segunda ordem
  (taxa vs. média da taxa), mais escopo novo sem necessidade comprovada.
- **6 KPIs numa linha só** -- rejeitada: ficaria apertado numa tela comum; duas linhas de `kpi_row()` (4 +
  2) reaproveitam o componente existente sem mudar sua assinatura.

## Consequências

- Esta ADR **supersede parcialmente a ADR 0024**: a decisão de AGREGAÇÃO/DADO da 0024 (`load_posts_content()`,
  função genérica de agregação por dia, `quebrar_em_segmentos` compartilhada) continua válida e inalterada;
  só a decisão de ONDE a seção de evidência mora muda (era "O que produzir", passa a ser "Resumo").
- `dashboard/screens/resumo.py`: remove `_melhor_post`, `_maior_alta_negatividade`,
  `_topico_alto_positivo_baixo_discurso`, `_contagem_publicacoes_recentes` e o bloco de render de 4 colunas
  dos destaques; ganha a seção de evidência (portada de `produzir.py`) e a segunda linha de KPIs de
  crescimento.
- `dashboard/screens/produzir.py`: perde a seção de evidência (fica só o link "Ver mais no Resumo"); ganha
  a nova seção "Destaques" (2 cartões) com as funções portadas de `resumo.py`.
- `dashboard/screens/radar.py`: ganha a leitura por período livre (portada de
  `resumo.py::_maior_alta_negatividade`, reaproveitando o filtro de calendário já existente na tela); o
  critério principal é redesenhado pela ADR 0025, não por esta.
- `dashboard/core/data.py`: nenhuma função nova exigida por esta ADR isoladamente (`load_growth_metrics()`
  já existe); `load_nsm_history()` é da ADR 0025.
- `tests/test_dashboard_screens_resumo.py`, `tests/test_dashboard_screens_produzir.py`,
  `tests/test_dashboard_screens_radar.py` precisam de casos novos refletindo a realocação de cada destaque.
- O filtro de calendário específico do destaque de negatividade some do cabeçalho do Resumo sem substituto
  ali -- continua existindo, mas dentro do Radar (reaproveitado, não duplicado).
