# Coletas

Convenções para extrair dados do Instagram e versioná-los no Hugging Face. Termos (**Coleta**, **Recorte**, **Snapshot**)
estão definidos em `CONTEXT.md`.

> Status: convenção implementada pelo módulo `src/coleta/` e pela CLI `coleta.py` (ADR 0039). Comandos: `coletar`,
> `publicar`, `restaurar`, `listar`, `baixar` (`uv run python coleta.py <comando> --help`). Sem `--yes`, `coletar`, `publicar`
> e `restaurar` só mostram a estimativa de custo ou o plano.

## Antes de extrair

- Extração real gasta dinheiro na Apify. **Nunca rode sem `--yes` e sem aval explícito do usuário no chat**, e mostre antes
  a estimativa de custo (pior caso).
- Extraia sempre em pasta de dados limpa (`DATA_DIR`), nunca por cima da pasta `data/` em uso.
- O **Recorte** pode combinar janela relativa, intervalo absoluto e teto por perfil. Confirme o Recorte com o usuário.

## Nome da tag de uma Coleta

```
coleta_<extração>[_<janela>][_<teto>][_<rótulo>]
```

| Segmento | Formato | Quando aparece |
|---|---|---|
| `<extração>` | `AAAA-MM-DD`, dia em que a extração rodou | sempre |
| `<janela>` relativa | `ultimos-90d`, `ultimos-12m` | Recorte com janela relativa |
| `<janela>` absoluta | `de-AAAA-MM-DD_ate-AAAA-MM-DD` | Recorte com intervalo absoluto |
| `<teto>` | `teto-<N>`, itens por perfil | Recorte com teto |
| `<rótulo>` | minúsculas, sem acento, com `-` (ex.: `piloto`) | opcional, escolhido pelo usuário |

Regras:

- Ordem fixa, a da tabela. Janela relativa e intervalo absoluto não aparecem juntos.
- Só minúsculas, dígitos, `-` e `_`; sem acento nem espaço.
- Dois nomes iguais (mesmo dia e mesmo Recorte) exigem um rótulo; nunca sobrescreva uma tag.
- A tag é um atalho legível. A verdade (Recorte pedido, cobertura real por perfil, contagens) fica no manifesto da Coleta.

Exemplos:

- `coleta_2026-10-09_ultimos-90d_teto-250`
- `coleta_2026-10-09_teto-10`
- `coleta_2026-10-09_de-2026-03-01_ate-2026-06-30_teto-50`
- `coleta_2026-10-06_piloto`

## Versionamento no Hugging Face

- O Snapshot de uma Coleta contém **Bronze, Silver e Gold** e um manifesto. Não há camada landing separada: a Bronze é fiel
  à Apify (guarda o item completo numa coluna bruta, sem descartar campos) e a validação e o parsing ficam na Silver.
- O manifesto traz identidade (tag, data e hora, versão do código), Recorte pedido, cobertura real por fonte e por perfil
  (contagens e datas mais antiga e mais recente), custo na Apify e a lista de tabelas derivadas com número de linhas.
  Não carrega conteúdo (nomes, textos) nem segredos.
- A `main` do dataset guarda **só a Coleta vigente**. Uma Coleta nova entra como um commit que substitui os arquivos da
  anterior; as anteriores continuam acessíveis por tag.
- **Nunca apague o commit de uma Coleta anterior** nem reescreva a `main` com force-push. Marque a Coleta antes de
  substituí-la.
- Restaurar uma Coleta antiga na `main` = baixar a tag e publicá-la como um novo commit (com tag nova).
  Em código: `restaurar(tag, cliente=..., confirmar=..., rotulo="restaurada")` em `src/coleta/hf.py` (tag nova = `<tag>` com rótulo `restaurada`, data = extração original).
- O dashboard publicado baixa a `main` (a Coleta vigente). A variável opcional `HF_DATASET_REVISAO` (tag ou commit) faz o
  app mostrar uma Coleta antiga, sem mexer na `main`. Trocar de Coleta = publicar a nova e reiniciar o app.
