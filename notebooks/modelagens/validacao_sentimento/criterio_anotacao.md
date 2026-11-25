# Critério de anotação de sentimento dos comentários

> Versão versionada: os exemplos que eram frases inteiras de comentários foram trocados por paráfrases; as decisões são as
> usadas na anotação.

Pergunta única: **que sentimento o texto do comentário expressa?** O anotador vê só o texto. Não sabe em que perfil o comentário
foi feito nem o que qualquer classificador respondeu. Os comentários são de perfis de governadores brasileiros no Instagram, em
período eleitoral (2026).

## Rótulos

| Rótulo | Quando usar |
|---|---|
| `positive` | Elogio, apoio, comemoração, bênção, declaração de voto ou de adesão ("estou com 15", "bora", "tem meu voto", "meu senador"), emojis de aplauso, coração, foguete, confirmação (✅) |
| `negative` | Crítica, insulto, rejeição ("fora X"), denúncia, lamento, tristeza, deboche ou ironia contra alguém, **cobrança** por omissão ou por serviço que não funciona, emojis de reprovação, tristeza ou nojo |
| `neutral` | Texto sem carga avaliativa: fato, pergunta sem indignação, **pedido** educado de ajuda, saudação simples, nome ou @ solto, propaganda, texto sem sentido, e os casos em que a polaridade **não pode ser decidida só pelo texto** |

## Casos difíceis (decisões fixas)

| Caso | Decisão | Exemplos |
|---|---|---|
| Número de candidato **sem** marcador afetivo | `neutral` (pode ser apoio ou provocação) | "22", "13 13", "Zema30", "Lula13", "13 Elmano", número em emojis seguido do nome do candidato, "1️⃣3️⃣🇧🇷" (bandeira não é marcador afetivo) |
| Número de candidato **com** marcador afetivo (emoji de apoio, "bora", "meu", "é", "vote", "pra cima") | `positive` | "5️⃣5️⃣💙🚀", "13 ❤️", "44 ✅", "Pra cima 44", "É 13!!!", "Estou com 15", "Meu senador João 400" |
| Só emojis de apoio (👏 ❤️ 💙 🚀 🙌 🙏 😍 💯 ✅) | `positive` | "👏👏👏", "🚀🚀" |
| Só 😂, 🔥, 🇧🇷, 😮 ou outro emoji ambíguo | `neutral` | "😂😂😂", "🔥", "🇧🇷🇧🇷" |
| Só emoji de tristeza ou reprovação (😢 😭 😔 👎 🤮 🤡 💔) | `negative` | "😢", "👎👎" |
| Cobrança ou protesto, mesmo em forma de pergunta | `negative` | "E os Guarani Kaiowá?", "cadê nossos salários", exigência de reforma de um equipamento público, de liberação de um serviço |
| Hashtag de protesto sozinha, sem frase | `neutral` | "#protejamnossospovosindígenas" |
| Pedido educado, sem acusação | `neutral` | pedido de exame, de convocação de concurso, de PIX, "Coloca pra gente baixar" |
| Alvo é um terceiro (Lula, STF, adversário, prefeitura) e não o dono do perfil | Rotula-se o sentimento do texto, seja qual for o alvo | "Fora Lula" → `negative`; "Bora Lula" → `positive` |
| Ironia, sarcasmo, deboche | Rotula-se o sentido pretendido | elogio irônico seguido de risada, dizendo que há quem acredite → `negative` |
| Dois sentimentos no mesmo texto | O dominante; se nenhum domina, `neutral` | declaração de voto com emoji de choro → `negative`; apoio a um e ataque a outro, sem dominante → `neutral` |
| Concordância ou constatação seca | `neutral` | "Verdade", "Fato.", "Já votei", "Elmano reeleito" (sem emoji) |
| Saudação simples | `neutral`; com afeto ou bênção, `positive` | "BOM DIA, GOVERNADOR!" → `neutral`; cumprimento com bênção e coração → `positive` |
