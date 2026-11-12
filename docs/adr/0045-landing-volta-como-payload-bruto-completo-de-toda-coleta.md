---
status: accepted
---

# A landing volta: o payload bruto completo e sem filtro de toda Coleta

## Contexto

A ADR [0039](0039-coleta-versionada-no-hf-bronze-fiel-e-aws-so-reconstroi.md) aboliu a landing separada: a Bronze passou a
guardar o item completo da Apify na coluna `_raw`, e a landing (`landing/<run_id>/*.json`) deixou de existir. Na prática isso
deixou de proteger o dado bruto em dois pontos, vistos na Coleta do TCC (2026-08-16 a 2026-10-25):

- **A Bronze é filtrada pelo Recorte.** O actor só filtra o início da janela; o fim é aplicado localmente depois, e o que
  fica fora nunca chega à Bronze. Foram cobrados e descartados 618 posts, 397 reels e 2.497 UGC. Eles só existiam nos
  datasets da Apify, que expiram (31 dias no plano Starter).
- **O dado bruto é o mais caro de refazer** (US$ 85,62 só nessa Coleta) e o que mais importa para reanalisar campos que a
  Bronze não extraiu. Depender da retenção de um serviço externo para tê-lo contraria o objetivo da Coleta versionada.

Além disso, a `landing/` que o HF mostrava na `main` era a da Coleta do Reboot (extraída antes da Bronze ter `_raw`); o
`publicar` não a tocava, e a revisão `tcc` exibia a landing de outra Coleta.

## Decisão

1. **Toda Coleta tem landing.** O `coletar` grava, **assim que cada actor devolve** e antes de qualquer filtro, o payload
   completo em `landing/<run_id>/{profiles,posts,reels,ugc_mentions}.json`: uma lista JSON por fonte, exatamente como a
   Apify devolveu (inclusive registros de erro como `no_items` e itens fora do Recorte). É o formato da landing do Reboot.
   Uma falha posterior (Bronze, UGC) não apaga o que já foi gravado; sem `--yes` nada é escrito.
2. **A Bronze não muda:** continua com `_raw` e continua filtrada pelo Recorte. A landing é a cópia fiel do que foi pago;
   a Bronze é a tabela de trabalho.
3. **Manifesto v6.** Bloco opcional `landing` com o `run_id` e, por fonte (`perfis`, `posts`, `reels`, `ugc`), `itens` e
   `bytes`. Sem campo nulo; Coletas sem landing não têm o bloco; v1 a v5 continuam válidas.
4. **`publicar` envia `landing/`** junto de Bronze, Silver e Gold e a inclui no plano e no limite de bytes. Como a `main`
   guarda só a Coleta vigente, publicar uma Coleta apaga da `main` a landing de outra (a anterior segue no histórico e nas
   tags de uso). O `publicar` recusa um Snapshot cuja landing não bate com o manifesto.
5. **`baixar` traz a landing** por padrão; `com_landing=False` a pula (a Lambda de reconstrução, que só precisa das camadas
   de dados, pula). `restaurar` a preserva.
6. **Coleta já extraída:** `coleta.py landing <pasta>` registra no manifesto a landing já presente na pasta (por exemplo,
   baixada dos datasets da Apify) e sobe o esquema para v6. Em seguida, `publicar --rotulo <novo>` gera uma publicação
   nova: o identificador já publicado nunca se repete, e as tags existentes continuam no commit onde foram criadas.

## Alternativas rejeitadas

- **Manter só a Bronze `_raw`:** não guarda o que o Recorte descarta e depende da retenção da Apify.
- **Gravar a landing só no HF, fora do Snapshot:** quebra a ideia de Coleta como um único commit e a deixa fora do manifesto.
- **Remover o filtro local do Recorte da Bronze:** misturaria itens fora do Recorte nas camadas de análise.

## Consequências

- Cada Coleta passa a ocupar muito mais espaço no HF (a do TCC tem ~590 MB de landing contra ~290 MB do resto).
- O dashboard (que baixa só Silver e Gold) não é afetado.
- A tag `tcc` fica no commit onde foi criada, sem a landing; a landing dessa Coleta entra por uma publicação nova.
