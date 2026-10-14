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

## Identificador de uma Coleta

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
- Dois identificadores iguais (mesmo dia e mesmo Recorte) exigem um rótulo; `publicar` recusa um identificador já publicado.
- O identificador vai na mensagem do commit (`push: <identificador>`) e no manifesto; **não é uma tag**. A verdade (Recorte pedido, cobertura real por perfil, contagens) fica no manifesto da Coleta.

Exemplos:

- `coleta_2026-10-09_ultimos-90d_teto-250`
- `coleta_2026-10-09_teto-10`
- `coleta_2026-10-09_de-2026-03-01_ate-2026-06-30_teto-50`
- `coleta_2026-10-06_ultimos-5d_teto-30`

## Versionamento no Hugging Face

- O Snapshot de uma Coleta contém **Bronze, Silver e Gold** e um manifesto. Não há camada landing separada: a Bronze é fiel
  à Apify (guarda o item completo numa coluna bruta, sem descartar campos) e a validação e o parsing ficam na Silver.
- O manifesto traz identidade (tag, data e hora, versão do código), Recorte pedido, cobertura real por fonte e por perfil
  (contagens e datas mais antiga e mais recente), custo na Apify e a lista de tabelas derivadas com número de linhas.
  Não carrega conteúdo (nomes, textos) nem segredos.
- `recorte` guarda o que foi **pedido** (`dias` ou `inicio`/`fim`, e `teto`); `recorte_efetivo` (esquema v2) traz a janela em
  datas, `{inicio, fim}`: `extração - dias` até a extração na janela relativa (aproximada, o actor conta a partir do instante
  da execução), ou o próprio intervalo no absoluto; `null` se o Recorte só tem teto. A `mais_antiga` da cobertura pode ser
  anterior ao `inicio` efetivo, porque itens fixados no perfil entram mesmo fora da janela. Manifestos v1 (sem o campo) continuam válidos.
- A `main` do dataset guarda **só a Coleta vigente**. Uma Coleta nova entra como um commit que substitui os arquivos da
  anterior; as anteriores continuam na história da `main`, acessíveis pelo identificador, pelo hash do commit ou por uma tag de uso.
- **Nunca apague o commit de uma Coleta anterior** nem reescreva a `main` com force-push (um `super_squash_history` descarta
  as Coletas que não tiverem tag). A única exceção é um pedido explícito do dono do dataset de recomeçar o histórico; nesse caso, guarde
  antes uma cópia local (`coleta.py baixar`) e registre o motivo.
- **Cada Coleta é um commit.** Os commits seguem o estilo do Git (`<tipo>: <descrição>`), com o identificador da Coleta na
  descrição: `push: <identificador>` ao publicar e `restore: <identificador>_restaurada` ao restaurar. `publicar` não cria tag.
- **Tags são só de uso**, escolhidas pelo usuário e criadas à mão no HF: `reboot-iesb` (apresentação no evento da IESB),
  `tcc`, `article-governor-segmentation`. Apontam para o commit de uma Coleta, não seguem a gramática `coleta_*` e nunca são
  movidas nem apagadas pelo projeto. `coleta.py listar` mostra, em cada Coleta, as tags de uso que apontam para ela.
- **O que acontece num push novo:** a `main` avança para o commit novo. Tags existentes continuam apontando para o commit onde
  foram criadas (não se sobrescrevem nem se movem) e tags novas se acumulam. Um commit só some da história se a `main` for
  reescrita; uma tag o mantém vivo.
- Restaurar uma Coleta antiga na `main` = baixá-la e publicá-la como um novo commit.
  Em código: `restaurar(referencia, cliente=..., confirmar=..., rotulo="restaurada")` em `src/coleta/hf.py`. A referência é um
  identificador `coleta_*` (resolvido para o commit mais recente que o publicou), uma tag de uso ou um hash de commit; o
  identificador novo é o original com o rótulo `restaurada`, e a data é a da extração original.
- O dashboard publicado baixa a `main` (a Coleta vigente). A variável opcional `HF_DATASET_REVISAO` (tag ou commit) faz o
  app mostrar uma Coleta antiga, sem mexer na `main`. Trocar de Coleta = publicar a nova e reiniciar o app.

## README do dataset (card do HF)

- O `README.md` na raiz do dataset é o card que o HF mostra. Ele **não faz parte do Snapshot**: `publicar` não o envia nem o
  apaga (só mexe em `bronze/`, `silver/`, `gold/` e `manifesto.json`). A cópia versionada no repositório é
  `docs/dataset/README.md`; a do HF é enviada à mão.
- **Todo push ou restore de Coleta deixa o card desatualizado.** Depois de publicar, atualize em `docs/dataset/README.md` o que
  descreve a Coleta vigente: a tabela "Coleta vigente" (identificador, commit, extração, Recorte, perfis, tags de uso), a
  cobertura e a linha do tempo (copie do `manifesto.json`), a nota de como o Recorte foi determinado (só vale para Coletas sem
  manifesto) e as observações da estrutura (`landing/`, coluna `_raw`, tabelas legadas). A convenção de commits e tags só muda
  quando a regra mudar.
- **O card segue junto com a Coleta**, no mesmo PR do HF (#275) que vai substituir a `main`, e nunca num commit só de docs.
  Enquanto o `publicar` não incluir o `README.md`, inclua-o no PR do HF à mão. Assim o card e a Coleta entram na `main` no mesmo
  commit, e o card pode citar o hash do commit da Coleta depois de mesclado.
- Se o card passar a ser gerado a partir do manifesto, registre aqui e remova a edição manual.
