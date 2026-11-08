---
status: accepted
---

# Coleta sem teto por padrão: o teto só existe quando o autor o pede

## Contexto

Até a ADR [0042](0042-custo-do-manifesto-estimado-por-media-mais-3-desvios-maximo-e-diferenca-percentual.md), toda Coleta
tinha um Teto aplicado: sem `--teto`, a CLI calculava um padrão (`max(200, 7 × dias)` com janela, 30 sem janela) e o
enviava ao scraper. Numa extração que quer **todo** o conteúdo de uma janela (o TCC: pré-campanha a eleições de 2026, 26
governadores) isso é um viés silencioso. No piloto, 2 governadores bateram o teto de 30 em 5 dias (6 ou mais itens por
dia); em 207 dias o padrão de 1.519 poderia cortá-los, e o corte cai nos itens mais antigos, a pré-campanha.

O schema de entrada dos actors de posts, reels e UGC (verificado na API da Apify em 2026-11-08) exige só `username`:
`resultsLimit` é opcional, inteiro, mínimo 1, sem `default` nem `maximum`. O comportamento quando ele é omitido não é
documentado; decidimos confiar no actor. O preço é por resultado entregue.

## Decisão

1. **Sem `--teto`, a Coleta é sem teto.** O Teto aplicado existe só quando o Recorte traz teto. O teto padrão por janela
   continua apenas para os scripts de backfill e é mantido, sob outro nome, só para ler Coletas anteriores.
2. **O scraper omite `resultsLimit`** nos actors de posts, reels e UGC e confia no comportamento do actor (decisão do
   autor, 2026-11-08; antes se pensou em enviar um sentinela de 1.000.000). A coleção de perfis mantém o limite próprio.
3. **Manifesto v5.** `custo.estimado.teto` vira `{"sem_teto": true}` e `maximo_usd` não existe (sem campos nulos). Os
   esquemas v1 a v4 continuam válidos; `sem_teto` só é aceito a partir da v5. A v5 também é a versão gravada pelas
   Coletas com teto (o bloco continua igual).
4. **Estimativa sem teto.** Não há Custo máximo. O Custo estimado é a soma projetada da Base de calibração mais 3·√N·σ,
   sem limite superior. Governador que bateu o teto da base usa a taxa observada, que é um piso. Base sem teto não
   censura ninguém; Base de uma Coleta anterior à v5 sem teto pedido é lida com o teto padrão de então.
5. **Sem teto e sem Base de calibração utilizável (em qualquer coleção) não há estimativa**: a CLI recusa, com erro, e
   manda informar `--teto` ou usar uma Coleta anterior como base.
6. **Aviso de truncamento** só roda quando houve teto.
7. **O freio passa a ser externo:** o limite de uso mensal da conta Apify. A CLI avisa isso na estimativa.

## Alternativas rejeitadas

- **Enviar um limite sentinela (1.000.000):** valor arbitrário; o autor preferiu confiar no actor.
- **Manter um teto padrão alto (ex.: 3.000):** continua sendo um corte que o autor não pediu.
- **`--orcamento-max`:** trava dentro do repo; fica para uma issue futura.
- **Estimar sem base com as taxas fixas da ADR 0012:** já abandonadas pela ADR 0042.

## Consequências

- Uma Coleta sem teto não tem gasto máximo garantido; o Custo estimado é uma previsão sem teto superior.
- Coletas já publicadas (v1 a v4, inclusive com `padrao: true`) continuam legíveis e podem servir de base.
- Um `coletar` sem `--teto` e sem Coleta anterior no HF passa a falhar: informe `--teto` na primeira Coleta.
- Se o actor aplicar um limite interno ao omitir o campo, a Coleta sai truncada sem aviso; confira a cobertura por perfil
  do manifesto depois da extração.
