---
status: accepted
---

# Adiar um sistema de `logging` estruturado; rodar `--run-modeling` agora com os `print`s existentes

## Contexto

O pipeline (`pipeline.py` e `src/`) usa hoje 33 chamadas a `print()` espalhadas para sinalizar
progresso (`[1/3] BRONZE: ...`, `[2/3] SILVER: ...`, etc.). Nenhum módulo usa o `logging` padrão do
Python — não há `logger`, `basicConfig`, nem handlers configurados em lugar nenhum do projeto.

Surgiu a necessidade de rodar `pipeline.py --run-modeling` pela primeira vez neste ambiente, para
validar o caminho end-to-end (`data/raw/*.json` → Bronze → Silver → Gold, incluindo
`governor_sentiment`/`governor_clusters`). Essa execução é pesada e sem GPU disponível (a placa é
uma AMD Radeon RX550, que não suporta CUDA; o `torch` instalado também é a build `+cpu`) — só o
embedding do BERTopic já está documentado em ~14 min (README), e os demais estágios (PCA,
`AutoClusterHPO`, sentimento via transformer) não têm tempo medido. Nesse cenário, acompanhar em
qual etapa o pipeline está tem valor real, não é só curiosidade.

A pergunta que motivou esta ADR: vale a pena trocar os `print`s por um sistema de `logging`
estruturado (níveis, timestamps por etapa, handler de arquivo) antes dessa primeira execução, ou
rodar já com o que existe e decidir o logging depois?

## Decisão

1. **Não implementar `logging` agora.** A execução de `pipeline.py --run-modeling` roda com os
   `print`s já existentes no código.
2. **Acompanhamento da execução fica a cargo do assistente**, informando o usuário a cada etapa do
   ETL (Bronze/Silver/Gold e cada estágio da modelagem: PCA, clustering, sentimento, tópicos) à
   medida que os `print`s do pipeline avançam — sem editar o código para isso.
3. Um sistema de `logging` (níveis INFO/DEBUG, timestamps por etapa, handler de console + arquivo
   por execução) fica registrado como melhoria futura, a ser feita como tarefa separada, fora desta
   sessão de execução.

## Por que

**Rodar primeiro, instrumentar depois.** O objetivo imediato é validar que o pipeline conclui
end-to-end contra os JSONs de `data/raw/` (Bronze/Silver/Gold recém-limpos para este teste) — uma
execução de verificação, não uma mudança de funcionalidade. Bloquear essa validação atrás de um
refactor de logging (~33 pontos de troca espalhados por `pipeline.py` e `src/modeling/*.py`, ainda
que mecânico e de baixo risco) inverte a prioridade: adiciona escopo não pedido antes de responder
à pergunta que motivou a sessão ("o pipeline roda ponta-a-ponta a partir do raw?").

**O `print` existente já é suficiente para o objetivo imediato.** Acompanhar progresso em uma
execução manual, única, observada interativamente não precisa de níveis de log, rotação de arquivo,
ou handlers — precisa só de alguém (aqui, o assistente, lendo a saída do processo) relatando cada
etapa conforme ela acontece. Um sistema de `logging` resolve um problema diferente: análise
posterior, comparação entre execuções, depuração sem supervisão em tempo real — nenhum desses é a
necessidade desta sessão.

**A necessidade real de `logging` fica mais clara depois de rodar pelo menos uma vez.** Ver o
pipeline `--run-modeling` rodar do início ao fim (com os tempos reais de cada estágio, não só o
`~14 min` documentado para o BERTopic) informa melhor o design do logging — por exemplo, se algum
estágio específico (PCA, `AutoClusterHPO`, sentimento) for desproporcionalmente lento, isso deveria
orientar onde entram os pontos de instrumentação mais finos, e essa informação só existe depois de
uma execução completa.

## Opções consideradas

- **Implementar `logging` antes de rodar** — rejeitada por ora: adia a validação que motivou a
  sessão para adicionar escopo não solicitado; melhor decidir o design do logging com dados reais de
  uma execução em mãos.
- **Não fazer nada e nunca revisitar `logging`** — rejeitada: os `print`s atuais não escalam para
  depuração assíncrona ou comparação entre execuções futuras; a ADR mantém isso como melhoria futura
  explícita, não descartada.

## Consequências

- `pipeline.py --run-modeling` roda nesta sessão sem nenhuma mudança de código.
- Nenhum arquivo de código foi alterado por esta decisão — só esta ADR.
- Fica registrado como trabalho futuro: substituir os 33 `print()` por `logging` padrão (INFO para o
  que os `print`s já mostram, DEBUG para detalhe adicional), com handler de console e,
  possivelmente, um arquivo de log por `run_id` em `data/model_checkpoints/<run_id>/` ou local
  equivalente — a ser desenhado quando essa tarefa for priorizada.
