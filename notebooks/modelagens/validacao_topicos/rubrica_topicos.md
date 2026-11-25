# Rubrica de avaliação qualitativa dos tópicos (camada 1)

Fontes: escala de 3 pontos de utilidade e coerência de Newman et al. (2010), cuja âncora é poder dar ao tópico um rótulo curto e
usá-lo para recuperar documentos; tipos de falha de Mimno et al. (2011); leitura de documentos e alinhamento entre palavras
e documentos de Doogan & Buntine (2021) e Grimmer & Stewart (2013). A separação entre coerência e utilidade para a
decisão é adaptação deste trabalho: Newman funde as duas numa escala só.

Contexto: tópicos BERTopic de um TCC sobre perfis de governadores brasileiros no Instagram, na campanha eleitoral de 2026.
- **comentarios**: o que o PÚBLICO escreve nos comentários (textos curtos, muitos só emojis).
- **legendas**: o que a ASSESSORIA do governador escreve nas legendas das publicações (as "pautas").

Para cada tópico você recebe as 10 palavras-chave e 15 documentos (3 representativos + 12 sorteados). Leia TODOS os
documentos antes de julgar. A decisão é sobre os documentos; as palavras são apoio.

## Passo 1, às cegas (sem consultar o rótulo do Gemini)

1. **rotulo_proprio**: rótulo curto (até 6 palavras) do que os documentos têm em comum, ou "NÃO ROTULÁVEL".
2. **docs_fora**: quantos dos 15 documentos NÃO se encaixam no seu rótulo (0 a 15).
3. **coerencia** (1 a 3):
   - 3 = os documentos tratam do mesmo assunto ou do mesmo ato comunicativo (ex.: pedir água, celebrar uma obra, anunciar
     voto), no máximo ~3 dos 15 fora, e as palavras refletem isso.
   - 2 = há um assunto dominante, mas com mistura relevante (4 a 7 fora), ou dois subassuntos próximos, ou palavras e
     documentos só parcialmente alinhados.
   - 1 = sem assunto comum identificável (8 ou mais fora), ou só ruído.
4. **tipo_falha** (só quando coerencia < 3; senão null), com as categorias de Mimno et al. (2011) e duas extras:
   - "encadeado": assuntos ligados por uma cadeia de palavras, nem todos os pares fazem sentido;
   - "intruso": dois conjuntos sem relação juntados, ou um bom tópico com alguns documentos ou palavras intrusos;
   - "aleatorio": sem conexão clara;
   - "desequilibrado": conectado, mas misturando termos muito gerais com muito específicos;
   - "ruido": dígitos, spam, letras repetidas ou textos sem conteúdo;
   - "grafia": o grupo se forma por forma de escrita (kkkk, tmj, emojis), não por assunto.
5. **alinhamento_palavras_docs**: "sim" | "parcial" | "nao". As 10 palavras descrevem o que os documentos dizem?
6. **utilidade** (1 a 3), definida pelo uso de uma assessoria de comunicação:
   - comentarios: 3 = identifica um assunto concreto, uma demanda, uma crítica ou uma reação a um objeto específico, sobre o
     qual a assessoria pode agir (responder, pautar, corrigir, amplificar); 2 = informa só uma reação genérica (apoio,
     afeto, aplauso, torcida sem objeto) ou uma mobilização repetida/copiada: diz "que tipo" de reação, não "sobre o quê";
     1 = sem valor para decisão (ruído, spam, sem assunto).
   - legendas: 3 = identifica uma pauta concreta da assessoria (tema, entrega, programa, evento, posicionamento), que
     pode ser comparada com outras pautas em desempenho e decidir o que produzir; 2 = pauta genérica demais (campanha em
     geral, agenda difusa) ou mistura de pautas; 1 = sem pauta identificável.
7. **categoria**: uma de "assunto_concreto" | "demanda_ou_critica" | "pauta_da_assessoria" | "reacao_generica" |
   "mobilizacao_repetida" | "ruido_spam" | "outro".
8. **justificativa**: até 30 palavras, citando o que nos documentos sustenta as notas.

Grave o passo 1 de TODOS os tópicos do lote antes do passo 2. Não altere notas do passo 1 depois.

## Passo 2: rótulo do Gemini

Só então abra o arquivo de rótulos do seu lote e, para cada tópico:
- **rotulo_gemini**: o texto do rótulo (copie);
- **rotulo_gemini_avaliacao**: "adequado" (descreve os documentos) | "parcial" (vago, ou cobre só parte) | "inadequado"
  (descreve outra coisa) | "sem_rotulo" (nulo);
- **rotulo_gemini_obs**: até 15 palavras.
