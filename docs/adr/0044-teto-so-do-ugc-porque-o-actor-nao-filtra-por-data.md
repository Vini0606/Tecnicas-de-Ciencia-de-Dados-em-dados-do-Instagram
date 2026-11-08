---
status: accepted
---

# Teto só do UGC: o actor de marcações não filtra por data

## Contexto

A ADR [0043](0043-coleta-sem-teto-por-padrao-teto-so-quando-explicito.md) tornou a Coleta sem teto por padrão, para não
enviesar posts e reels. Mas o actor de UGC (`apify/instagram-tagged-scraper`) aceita só `username` e `resultsLimit`
(schema verificado na API da Apify em 2026-11-08): **não há filtro de data**. O `onlyPostsNewerThan` que a Coleta envia aos
outros actors é ignorado por ele. Sem teto, o UGC devolve todo o histórico de marcações de cada governador; os itens fora
da janela só são descartados localmente, depois de cobrados. O custo do UGC fica sem limite e imprevisível, e o limite de
uso mensal da conta Apify (US$ 100 no plano Starter) pode pausar a extração no meio.

O `--teto` era um só para as três coleções: não havia como limitar apenas o UGC.

## Decisão

1. **`--teto-ugc N`**: teto de itens por perfil **só da coleção UGC**. Vale no UGC no lugar do `--teto` geral (se os dois
   forem informados, o UGC usa o seu). Posts e reels seguem a regra da ADR 0043: o `--teto` geral, ou nenhum.
2. **Não conta como critério de Recorte.** Sem janela, só `--teto-ugc` é recusado (Recorte vazio): posts e reels ficariam
   ilimitados.
3. **O feed de marcações vem do mais novo ao mais antigo**, então `N` pega as marcações mais recentes e cobre a janela de
   trás para a frente. O autor escolhe `N` grande o bastante e confere, depois, a data mais antiga de UGC por perfil.
4. **Identificador**: `coleta_<extração>[_<janela>][_<teto>][_<teto-ugc>][_<rótulo>]`, com `teto-ugc-N` só quando houver.
   O rótulo continua proibido de começar com `teto-`.
5. **Manifesto (esquema v5, extensão compatível)**: `recorte.teto_ugc` quando pedido; em `custo.estimado.teto`, a chave
   `ugc_itens_por_perfil`. Sem teto geral, o teto vira `{"sem_teto": true, "ugc_itens_por_perfil": N}` e o máximo só do UGC
   vai em `custo.estimado.maximo_ugc_usd` (o total continua sem máximo). Com teto geral, `maximo_usd` usa o teto de cada
   coleção. Sem `--teto-ugc` o manifesto é idêntico ao de antes. Os esquemas v1 a v5 continuam válidos.
6. **Estimativa**: cada coleção usa o seu teto. A Base de calibração guarda o teto próprio do UGC da Coleta de origem
   (`base_teto_ugc`); um perfil que chegou ao teto dela está censurado, por coleção.
7. **Aviso pós-extração**: o aviso de perfis truncados compara cada coleção com o seu teto e, para o UGC, mostra a data da
   marcação mais antiga de cada perfil truncado, para o autor ver se o corte ainda está dentro da janela.

## Alternativas rejeitadas

- **Trocar de actor** (`apify/instagram-scraper`, `resultsType: "mentions"`): muda a fonte e o preço; a ADR 0020 escolheu o
  tagged por reprodutibilidade. Só com um piloto que compare os resultados.
- **Tetos para posts e reels por coleção**: fora do escopo; o problema é só do UGC.
- **Deixar o UGC para outra Coleta**: possível, mas separa os dados do mesmo período.

## Consequências

- O UGC passa a ter um custo máximo garantido; posts e reels continuam sem máximo.
- Se algum governador tiver mais marcações no período do que `N`, as mais antigas da janela (a pré-campanha) ficam de fora.
  O aviso e a cobertura por perfil do manifesto mostram isso; a escolha de `N` pede uma sondagem de 1 a 3 governadores.
