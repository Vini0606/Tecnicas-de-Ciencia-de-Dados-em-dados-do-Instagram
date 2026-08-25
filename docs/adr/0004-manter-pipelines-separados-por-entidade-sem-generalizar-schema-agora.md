---
status: accepted
---

# Manter pipelines e dados separados por entidade política, adiando a generalização do schema até a implementação de uma segunda entidade

## Contexto

O roadmap do projeto (registrado no `/handoff`) inclui uma frente de "multi-entidade": generalizar a metodologia híbrida de NLP hoje aplicada aos 27 governadores para outras entidades políticas, com deputados como primeiro caso concreto cogitado. Hoje "governador" está hardcoded em três lugares: os nomes das tabelas Gold (`governor_engagement`, `governor_sentiment`, `governor_clusters`), o arquivo de entrada `governadores.xlsx`/`GOVERNADORES_FILE`, e as referências em `delta_repository.py`. A interface abstrata `DataRepository` (`load_profiles`, `load_posts`, `load_reels`, `load_comments`) já é genérica — nenhum método carrega nome de governador.

A planilha de entrada `governadores.xlsx` já carrega metadados como `Partido` e `Unidade Federativa` (estado), mas o pipeline hoje descarta tudo isso: `notebooks/01_extracao_e_limpeza_de_dados.ipynb` lê a planilha inteira só para extrair a coluna `Link` (`settings.LINK_COLUMN`) e montar a lista de perfis do Instagram a coletar. Partido e estado nunca chegam a Bronze, Silver ou Gold.

## Decisão

- Quando uma segunda entidade (ex.: deputados) for adicionada, ela roda pelo mesmo pipeline mas gera dados **completamente separados** dos governadores — tabelas/diretórios próprios, sem um dataset unificado nem um dashboard comparativo de saída.
- Reconhecemos, mas **não desenhamos agora**, a necessidade de capturar metadados de entidade (partido, estado, cargo) desde a entrada — hoje descartados — para viabilizar cruzamento futuro entre entidades (ex.: comparar engajamento por partido ou por estado, atravessando governadores e deputados). O schema exato desses metadados (nome das colunas, em qual camada do Medallion entram, como cada entidade referencia partido/estado) fica para quando a segunda entidade for implementada de fato.
- **Nenhuma mudança de código acontece agora.** `governor_*` (tabelas Gold), `GOVERNADORES_FILE` e as referências a governador em `delta_repository.py`, `checkpoint.py` e `orchestration.py` continuam como estão até o dia em que uma segunda entidade for de fato implementada.

## Por que

Ainda não existe uma segunda entidade real sendo coletada — desenhar hoje o schema de metadados compartilhado (partido, estado, cargo) ou renomear as tabelas `governor_*` para algo genérico seria decidir sobre um caso de uso hipotético, sem um caso real para validar o desenho (deputados são 513 pessoas e têm atributos sem equivalente direto em governador, como câmara/legislatura). Renomear/migrar agora tem custo real — mudança em `config/settings.py`, `delta_repository.py`, testes, e nos ADRs [0001](0001-separar-modelagem-em-etapas-deterministicas-e-refinamento-manual.md)-[0003](0003-desacoplar-modelagem-do-notebook-via-scripts-cli-com-checkpoint.md) que já referenciam esses nomes — pago antes de haver qualquer benefício, com risco de re-trabalho se o desenho mudar quando o caso real aparecer.

Ainda assim, vale registrar a intenção agora: sem isso, fica fácil não perceber que o pipeline já descarta partido/estado hoje, e repetir esse mesmo problema ao integrar uma segunda entidade sem sequer considerar o cruzamento futuro.

## Opções consideradas

- **Dataset unificado com coluna `entity_type` desde já** — rejeitada: nenhuma comparação cross-entidade era um requisito confirmado antes desta sessão; um schema único aumenta o acoplamento de `ModelEnricher`/`EngagementAggregator` a um caso de uso ainda hipotético.
- **Desenhar o schema de metadados compartilhado (partido/estado/cargo) em detalhe nesta sessão** — rejeitada por ora: sem uma segunda entidade real para validar contra, o desenho corre risco de over-engineering.
- **Agir agora — renomear `governor_*`/`GOVERNADORES_FILE` para algo genérico e já capturar partido/estado para os governadores existentes** — rejeitada: paga o custo da migração (dados, código, testes, ADRs anteriores) antes de qualquer entidade nova existir; é mais barato fazer essa migração junto com a implementação real de deputados, quando o desenho puder ser validado contra um caso concreto.

## Consequências

- Partido e estado continuam sendo descartados na leitura de `governadores.xlsx` até que a generalização seja de fato implementada — nenhuma análise por partido/estado é possível hoje, mesmo para os governadores atuais.
- Quando uma segunda entidade for implementada, o trabalho de capturar metadados de entidade, decidir onde vivem no Medallion, e potencialmente renomear `governor_*` precisa ser feito do zero — este ADR não adianta nenhuma dessas peças, só documenta que a decisão de fazê-las junto (e não antes) foi deliberada.
- Novas entidades continuam isoladas por padrão — qualquer cruzamento entre governadores e deputados (por partido, estado, etc.) exigirá trabalho explícito de unificação quando for de fato necessário, não vem "de graça" da arquitetura atual.
