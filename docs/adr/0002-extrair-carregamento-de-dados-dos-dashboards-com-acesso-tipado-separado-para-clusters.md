---
status: accepted
---

# Extrair o carregamento de dados dos dashboards para `src/dashboard/loaders.py`, com acesso tipado separado para a capacidade exclusiva do Delta

## Contexto

Hoje `pages/01_exploratory.py` e `pages/02_modeling.py` cada um define seu próprio `load_data()` decorado com `@st.cache_data`, construindo um `DeltaRepository` internamente e carregando um bundle de tabelas (perfis+comentários+reels numa página, comentários+reels+clusters na outra). Como são funções distintas, o cache do Streamlit não é compartilhado entre páginas — `reels_clean`, por exemplo, é lido do Delta Lake duas vezes por sessão, uma por página, mesmo as duas pedindo os mesmos dados. `charts.py`, por comparação, já é puro (recebe DataFrame, devolve `go.Figure`, sem I/O nem dependência de Streamlit) e tem teste implícito de manter essa pureza.

Além disso, `load_clusters()` só existe em `DeltaRepository` — não está na interface abstrata `DataRepository` (`src/repositories/base.py`), e nem `S3DataRepository` nem `ExcelDataRepository` o implementam, porque clusters são um artefato exclusivo da camada Gold do pipeline Medallion, produzido pelo notebook de modelagem. `S3DataRepository` já existe como implementação alternativa real (não hipotética) do mesmo `DataRepository`.

## Decisão

Criar `src/dashboard/loaders.py` com funções cacheadas granulares por tabela (`load_profiles()`, `load_comments()`, `load_reels()`, `load_clusters()`), cada uma decorada com `@st.cache_data`, em vez de um `load_data()` por página. Como as páginas passam a chamar a mesma função, o Streamlit deduplica o cache entre elas automaticamente.

Por trás dessas funções, dois construtores de repositório cacheados com `st.cache_resource`:

- `get_repository() -> DataRepository` — usado por `load_profiles`, `load_comments`, `load_reels`. Tipado pela interface abstrata.
- `get_delta_repository() -> DeltaRepository` — usado só por `load_clusters()`. Tipado pelo concreto, e levanta um erro claro se o backend configurado não for Delta.

`src/repositories/base.py` **não muda** — `load_clusters` continua fora da interface abstrata.

## Por que

Separar em dois construtores, em vez de tipar tudo por `DataRepository` (exigindo `load_clusters` na interface, com stub `NotImplementedError` em `S3DataRepository`/`ExcelDataRepository`) ou tudo por `DeltaRepository` (trancando o módulo inteiro no backend concreto), preserva o Strategy pattern que `DataRepository`/`S3DataRepository` já implementam para as três tabelas que toda implementação de fato tem, sem fingir que `load_clusters` é uma capacidade genérica de "repositório de dados processados" quando na verdade é específica do Delta/Gold. Se um dia o dashboard trocar de `DeltaRepository` para `S3DataRepository`, três dos quatro loaders continuam funcionando sem mudança — só `load_clusters()` fica explicitamente marcado como dependente do Delta.

Funções granulares por tabela (em vez de um bundle por página) elimina releitura redundante do Delta Lake entre páginas na mesma sessão, de graça, só por reaproveitar o cache do Streamlit — não é só uma questão de duplicação de código.

## Opções consideradas

- **Um `load_data()` por página (bundle), só extraindo a construção do repositório para um helper comum** — rejeitada: resolveria a duplicação de código, mas não a releitura redundante entre páginas, já que funções diferentes não compartilham cache no Streamlit mesmo pedindo os mesmos dados.
- **Adicionar `load_clusters` à interface abstrata `DataRepository`**, com stub `NotImplementedError` em `S3DataRepository`/`ExcelDataRepository` — rejeitada: prometeria uma capacidade que só uma implementação tem de verdade, e `S3DataRepository` é um backend real (não hipotético) que este projeto pode querer usar.
- **Tipar `get_repository()` inteiramente como `DeltaRepository` concreto** — rejeitada: trancaria todos os quatro loaders no backend Delta, quando só `load_clusters()` de fato precisa disso.
- **Colocar as funções de loader dentro de `src/visualization/`** (irmãs de `charts.py`) — rejeitada: quebraria a pureza de `charts.py`/`visualization/` (hoje sem I/O nem dependência de Streamlit), misturando responsabilidades num módulo que serve de referência de "camada de apresentação sem efeito colateral".
- **Colocar em `pages/_shared.py`** — rejeitada: `pages/` não tem nenhum teste hoje; manter a lógica de cache em `src/` segue a convenção do resto do repo (tudo em `src/` é testável e testado).

## Consequências

- `src/dashboard/` passa a existir como um novo subpacote, com convenção de teste equivalente à de `src/repositories/` (ver `tests/test_delta_repository.py`) — cobrindo a composição (`get_repository`/`get_delta_repository` resolvendo pro tipo certo, erro claro quando mal configurado), não a leitura do Delta em si, já coberta.
- `pages/01_exploratory.py` e `pages/02_modeling.py` passam a importar de `src/dashboard/loaders.py` em vez de instanciar `DeltaRepository` diretamente.
- Se uma futura página precisar de uma tabela ainda não exposta por `loaders.py`, a extensão é aditiva (nova função `load_x()`), não uma reestruturação.
