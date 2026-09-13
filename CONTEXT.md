# Tecnicas de NLP em dados do Instagram

Pipeline Medallion (Bronze/Silver/Gold em Delta Lake) que coleta, modela e apresenta métricas de
engajamento, sentimento e tópicos dos perfis de Instagram de governadores brasileiros, entregue como
um dashboard Streamlit de growth para analistas de assessoria.

## Language

**Tela**:
Uma página do dashboard organizada em torno de uma única decisão do analista de assessoria ("o que
eu posto a seguir?"), não em torno de uma tabela ou técnica de modelagem.
_Avoid_: Página, aba, view (quando falando do produto ao usuário final; "página"/`pages/` ainda é
termo técnico válido para arquivos Streamlit).

**Frase de decisão** (faixa de decisão / decision band):
A frase em destaque no topo de cada tela, numa faixa colorida por semáforo, que responde
"e agora, o que eu faço?" antes de qualquer gráfico. Sempre a primeira coisa lida na tela.
_Avoid_: Título, headline, insight.

**Grupo de desempenho**:
Rótulo de negócio para um cluster de conteúdo ou de perfil (ex.: "curto, converte"; "alto alcance,
baixa conversão"). O rótulo é curado a partir do perfil real do cluster, nunca o ID numérico bruto —
`cluster_label == -1` (ruído do DBSCAN) vira "casos atípicos / virais", nunca aparece como "-1".
_Avoid_: Cluster (termo técnico, não aparece na interface do usuário final).

**Selo de confiabilidade**:
Marcação discreta ("em validação", "ilustrativo — histórico curto", "agrupamento experimental",
"piloto") que acompanha uma métrica cuja confiabilidade ainda não foi totalmente estabelecida contra
dado real. Nunca cosmético — é o que distingue esta ferramenta de um gerador de números falsamente
precisos (ver ADR 0021, Parte 4 da especificação de origem).
_Avoid_: Badge, tag, aviso genérico.

**Estágio** (do funil COBRA-RACE):
Um dos quatro momentos da jornada do público mapeados no dashboard: Reach·Alcançar,
Act·Consumir, Convert·Contribuir, Engage·Criar. Cada tela do dashboard carrega um rótulo de estágio
discreto no cabeçalho, mesmo quando não é a tela dedicada ao funil.
_Avoid_: Etapa, fase, nível (usar "estágio" para RACE; "nível" é o termo do framework COBRA
subjacente, ambos coexistem no rótulo "Estágio · Nível").

**Gargalo**:
O estágio do funil com a menor taxa de passagem entre execuções, entre os estágios que têm dado real
(Convert→Engage nunca é gargalo, pois Engage não tem dado real hoje — ver "Visualizações" vs.
"alcance"). Destacado em amarelo na tela do funil.
_Avoid_: Bottleneck, ponto fraco.

**Visualizações** (Reach real):
Soma de `videoPlayCount` (views reais dos Reels) usada exclusivamente no estágio Reach da tela do
funil. Um dado real coletado do Instagram — diferente de "alcance", que é sempre uma estimativa.
_Avoid_: Alcance (reservado para a métrica estimada, ver abaixo) — os dois nunca são a mesma coisa
nem usam o mesmo rótulo em nenhuma tela.

**Alcance** (estimado por engajamento):
Proxy de alcance usado por NSM e Score ICE, calculado a partir de engajamento (curtidas + respostas),
porque o Instagram não expõe alcance real para essas métricas. Sempre acompanhado do tooltip
"estimativa baseada em engajamento".
_Avoid_: Reach, visualizações, views (reservados para o dado real do funil, ver acima).

**Engajamento qualificado** (rótulo de usuário para NSM/North Star Metric):
Nome exibido ao analista de assessoria para a NSM — comentários positivos sobre comentários totais,
ponderado pelo alcance-proxy. Sempre acompanhada do selo "em validação" até confirmação contra os 27
perfis reais.
_Avoid_: NSM (sigla técnica, nunca aparece sozinha na interface do usuário final; ok em código/ADR).
