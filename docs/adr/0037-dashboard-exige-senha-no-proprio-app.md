---
status: accepted
---

# O dashboard exige senha no próprio app

## Contexto

Na auditoria do app publicado no Streamlit Community Cloud (2026-10-08), a restrição de visualizadores do Cloud
protegia só a URL principal: `/` redireciona para o login do Streamlit (HTTP 303), mas o caminho interno `/~/+/`
respondia 200 sem autenticação, e o WebSocket `/~/+/_stcore/stream` aceitava o handshake (HTTP 101). Uma sessão sem
nenhum cookie executou o app e recebeu o conteúdo da tela, ou seja, qualquer pessoa com a URL conseguia usar o
dashboard, que mostra comentários de terceiros, métricas de UGC e o Scorecard. O comportamento é da plataforma, e não
do código do repositório, mas o app não tinha nenhuma autenticação própria.

## Decisão

1. **Senha no próprio app.** `dashboard/core/acesso.py::exigir_acesso()` roda no topo de `dashboard/app.py`, antes
   do download dos dados do Hugging Face (ADR 0036) e de qualquer tela. Enquanto a senha não for informada, só o
   formulário é renderizado e a execução para (`st.stop()`); nem a navegação das telas aparece, e os dados nem são
   baixados por uma sessão não autenticada.
2. **Falha fechada.** Com `APP_PASSWORD` (Secrets ou `.env`), o app sempre pede a senha. Sem ela, só libera em
   `localhost`, `127.0.0.1` e `[::1]` (cabeçalho `Host`); em qualquer outro host mostra "Acesso não configurado" e
   bloqueia. Assim, um deploy sem o Secret nunca fica aberto por esquecimento. Com a senha configurada, a regra de
   `localhost` não se aplica, então forjar o `Host` não abre o app.
3. **Comparação em tempo constante** (`hmac.compare_digest` sobre o SHA-256 das duas senhas, sem vazar o tamanho) e um
   atraso de 1 segundo a cada tentativa errada.
4. A sessão liberada fica em `st.session_state`: recarregar a página pede a senha de novo.

## Consequências

- **Credenciais:** `APP_PASSWORD` nos Secrets do app. É uma senha compartilhada: não há contas por pessoa, nem como
  revogar o acesso de uma pessoa só (só trocando a senha para todos).
- O atraso de 1 segundo não impede tentativas paralelas em escala, então a senha precisa ser longa. Se for preciso
  acesso por pessoa, o caminho é `st.login` (OIDC), que exige configurar um provedor e fica fora desta ADR.
- A restrição de visualizadores do Cloud continua útil como primeira camada, mas não deve ser tratada como proteção
  dos dados.
- Dado sensível: se o dashboard não precisar do texto dos comentários de terceiros, o melhor é não publicá-los no
  dataset do Hugging Face (ADR 0036). Esta ADR protege o acesso ao app, não minimiza os dados.
