---
status: accepted
---

# Custo do manifesto: estimado por média + 3 desvios, máximo pelo teto e diferença percentual

## Contexto

O manifesto da Coleta (ADR [0039](0039-coleta-versionada-no-hf-bronze-fiel-e-aws-so-reconstroi.md)) guardava um bloco
`custo.estimado` plano (esperado e pior caso misturados, sem unidade no nome) e um `custo.real`. Na Coleta piloto
(`coleta_2026-10-06_ultimos-5d_teto-30`) o estimado esperado foi US$ 6,04 contra US$ 3,72 reais, quase tudo por causa do
UGC: sem calibração, a estimativa assumia o teto cheio em todos os perfis (780 itens) e vieram 246. As taxas fixas da
ADR 0012 também superestimavam posts e reels em janelas curtas. A
calibração por governador (issue #299) só valia com Coleta anterior de 30 dias ou mais.

Dados do piloto (26 governadores): média e desvio entre governadores são grandes (UGC 9,0 ± 9,9 itens). Aplicar
"média + 3σ" **por perfil** estoura o teto (39 itens > 30) e reproduz o pior caso; aplicado ao **total**
(`3·√N·σ`) dá 385 itens de UGC, ~40% acima do real.

## Decisão

1. **Esquema v4 do manifesto**, com `custo` agrupado por origem e unidade no nome de cada chave:
   - `estimado`: `estimado_usd` (média + 3σ), `maximo_usd` (teto cheio), `resultados_itens` (itens estimados),
     `teto` (`aplicado_itens_por_perfil`, `padrao`) e `base_calibracao` (de onde veio cada coleção).
   - `real`: `custo_usd` e `resultados_itens`, por coleção, do que a Apify cobrou.
   - `diferenca`: `custo_pct` e `resultados_pct`, `(real − estimado) / estimado × 100`, **só percentual**.
   - Cada bloco por coleção (`perfis`, `posts`, `reels`, `ugc`) mais `total`. Todos em US$ (a Apify cobra em dólar; nada
     é convertido para reais) ou em itens. Nenhum campo nulo. v1 a v3 continuam válidos.
2. **Custo estimado = média + 3σ sobre o total**, nunca acima do máximo: `soma dos valores projetados de cada
   governador + 3·√N·σ`, com σ o desvio entre os valores projetados. Não há "esperado" separado. Consequência aceita:
   a `diferenca` é quase sempre negativa e mede a **folga do orçamento**, não o erro da previsão.
3. **Custo máximo = Teto aplicado cheio** em todos os perfis. O teto padrão, sem `--teto`, é `max(200, 7 × dias)` com
   janela (era `10 × dias`; valia também para o teto enviado ao scraper) e 30 sem janela; o manifesto grava o teto
   aplicado e se veio do padrão.
4. **Base de calibração** é a Coleta anterior mais recente do HF, **por menor que seja a janela**. Projeção para o novo
   Recorte: posts e reels pela taxa diária de cada governador × dias, limitada ao novo teto; UGC (independe da janela)
   pela contagem da base; governador que bateu o teto da base é censurado e sobe ao novo teto; governador ausente da base
   entra com a média dos demais. Sem base (ou base zerada na coleção, ou Recorte sem janela para posts e reels), o
   estimado é o máximo da coleção e a `base_calibracao` diz `sem_base`. Perfis: um resultado por governador, sem
   calibração. As taxas fixas da ADR 0012 deixam de entrar na estimativa.
5. **O custo real vem do run finalizado** (`usageTotalUsd` ou, se vazio, eventos cobrados × preço do evento) e é gravado
   na hora: os runs somem da Apify em 7 dias no plano FREE.

## Alternativas rejeitadas

- **Média + 3σ por perfil:** limitada ao teto, iguala o pior caso nos dados do piloto e não informa nada.
- **Esperado e provável alto separados:** o usuário preferiu um único estimado (o alto), mesmo tornando a diferença
  negativa por construção.
- **Valores em reais (BRL):** exigiria cotação por dia; o pipeline inteiro é em US$.
- **Manter 30 dias mínimos de janela na base:** deixaria o UGC (que não depende da janela) sem calibração.
- **Diferença absoluta além da percentual:** derivável dos dois blocos.

## Consequências

- Manifestos v4 são maiores, mas autoexplicativos: o teto, a base e a unidade ficam no próprio arquivo.
- Com base curta (piloto de 5 dias) posts e reels projetados para 90 dias saturam no teto; só o UGC cai de verdade
  (US$ 17,55 → ~US$ 1,04 no teto 250). Uma base de 90 dias melhora posts e reels nas Coletas seguintes.
- A estimativa de σ com 5 dias de base multiplica o ruído por 18; tratar o estimado de posts e reels, nesse caso, como
  o máximo na prática.
- Nove governadores do piloto vieram com exatamente 21 itens de UGC (suspeita de limite do actor, ainda não
  investigada): a base de UGC pode subestimar quem tem muitas marcações.
- O manifesto da Coleta piloto no HF está em v3 (custo no formato antigo) até ser convertido.
