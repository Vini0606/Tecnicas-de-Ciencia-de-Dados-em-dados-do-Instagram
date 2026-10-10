---
status: accepted
---

# Correções da auditoria do app publicado: rótulos legíveis, amostra mínima e privacidade

## Contexto

A auditoria do app no Streamlit Cloud (2026-10-08) encontrou, além do acesso sem login (ADR 0037), problemas de
qualidade e de privacidade nas telas:

- "Melhor aprovação 100%" vinha de um perfil com **3 comentários**; a mediana é 302 por governador.
- Os tópicos de comentário são quase todos emojis convertidos em palavras ("mãos aplaudindo pele clara", "tecla 3 tecla 2",
  "coração vermelho"): 28% dos comentários positivos de um governador apareciam com esse nome, e o Radar mostrava o
  nome bruto do BERTopic (`25_defendam_incontestáveis_reconheço_227`).
- Nomes de pauta e de tópico traziam menções `@usuario` de cidadãos (ex.: `arthurhenriquerr`).
- Cada visita enviava telemetria de uso do Streamlit (POST ao webhook do Streamlit).
- A página declara `lang="en"` com conteúdo em português, e o SVG do funil não tem descrição acessível.
- O aviso de "Agrupamento experimental" dizia "27 perfis reais", mas são 26.

## Decisão

1. **Amostra mínima nos cartões.** "Melhor aprovação" e "Maior rejeição" só consideram perfis com pelo menos
   `MIN_COMENTARIOS_CARTAO = 30` comentários e mostram o nº de comentários ("João Azevêdo · 479 comentários"). Sem
   nenhum perfil elegível, o cartão diz isso. O valor 30 é um piso prático, não um teste estatístico.
2. **Rótulos de tópico em `dashboard/core/rotulos.py`** (funções puras): tira o prefixo de id e troca `_` por vírgula
   (Radar); tópicos que são (pelo menos 75% das palavras, ignorando ligações) só descrição de emoji ganham nome legível por
   família ("Emojis de mãos e aplausos", "de corações", "de rostos", "de números", "de bandeiras e símbolos", ou "Reação
   só com emojis"), usado nos grupos de comentários de "O que produzir" e no Radar.
3. **Menções de terceiros fora dos nomes.** `data.mencoes_de_terceiros()` extrai `@usuario` (8 caracteres ou mais, para
   não tirar palavras comuns como `@brasil`) dos comentários e das legendas, **exclui os perfis dos próprios
   governadores** (figuras públicas) e os loaders de `governor_sentiment(_history)`, `governor_discourse_topics`,
   `topic_priority_score` e `content_topic_priority_score` removem essas palavras da coluna `Name`. Hashtags não são
   menções e ficam: `#JoãoPraTodaObra` e `#TôComRiedel` são lemas de campanha públicos.
4. **Sem telemetria:** `.streamlit/config.toml` com `gatherUsageStats = false`.
5. **Acessibilidade:** `<html lang>` passa a `pt-BR` (um iframe de altura 0 ajusta a página pai, escondido por CSS), e o
   SVG do funil ganha `role="img"` e `aria-label` com os três valores.
6. **Texto:** o aviso do agrupamento deixa de fixar o número de perfis. O rótulo "Casos atípicos / virais" para o
   cluster de ruído **não muda**: o nome é fixado pelo `CONTEXT.md` e pelo dicionário de dados.

## Consequências

- **Limite do filtro de menções:** o popup de comentários mostra o texto original, que pode conter `@usuario` de terceiros;
  esta ADR só limpa os **rótulos**. O texto dos comentários continua sendo o ponto de privacidade mais sensível (ADR 0037).
  Menções com menos de 8 caracteres não são tratadas.
- **Heurística de emoji:** o vocabulário é uma lista fixa de palavras de descrição de emoji em português. Um tópico
  de texto com muitos emojis pode ser rotulado como emoji, e um emoji fora da lista mantém o nome bruto.
- **Google Fonts (Inter)** continua sendo carregado de `fonts.googleapis.com`, o que expõe o IP do visitante ao Google. Hospedar
  a fonte no app resolveria, e não foi feito aqui.
