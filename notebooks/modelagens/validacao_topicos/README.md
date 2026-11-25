# Avaliação dos tópicos BERTopic (Seção 5.5.3 do TCC)

Avaliação em três camadas dos dois modelos de tópicos do checkpoint `20261118_151001_8f41855c` (comentários: 49 tópicos;
legendas: 198 pautas). Nenhum script reajusta o modelo: todos leem o checkpoint persistido.

| Camada | O que mede | Arquivos |
| :--- | :--- | :--- |
| 1. Leitura por rubrica | coerência de assunto, pureza (fração de documentos que cabem no rótulo), utilidade para a assessoria, tipo de falha, adequação do rótulo Gemini | `rubrica_topicos.md`, `prep_amostras.py`, `anotacao_*.json`, `rotulos_*.json`, `conferencia_topicos.xlsx` |
| 2. Validade convergente e externa | sentimento por categoria (Gold, classificador ajustado da ADR 0049), concentração por perfil, semana e autor | `camadas_2_3.py`, `metricas_*.csv` |
| 3. Métricas automáticas | NPMI (documento, comentários por publicação, janela de 10, variantes de sensibilidade) e diversidade, com piso aleatório | `npmi_diversidade.py`, `camadas_2_3.py`, `npmi_diversidade.json`, `resumo_camada3.json` |

Anotação: modelo de linguagem (Claude), um anotador por lote de tópicos (2 lotes de comentários, 6 de legendas), às cegas
quanto a tamanho, sentimento, perfil, métrica e rótulo do Gemini; conferida pelo autor (registro em `conferencia_topicos.xlsx`).

Ordem de execução (venv Py3.12 com o BERTopic do checkpoint, `PYTHONPATH` na raiz do repo, `HF_HUB_OFFLINE=1`):

1. `python npmi_diversidade.py <repo> <run_id> npmi_diversidade.json`
2. `python prep_amostras.py <repo> <run_id> <pasta>`: gera os lotes cegos `lote_*.json` (textos reais, fora do repositório)
3. anotação dos lotes segundo `rubrica_topicos.md`, gravando `anotacao_*.json`
4. `python camadas_2_3.py <repo> <run_id> <pasta>`
5. exportar `id_comment`, `Topic` e `sentiment_label` dos comentários da Gold `governor_sentiment` para `gold_sent.parquet`
6. `python consolidar.py <pasta dos lotes e anotações> <pasta das métricas>`

Privacidade: `lote_*.json`, `gold_sent.parquet` e `conferencia_topicos.xlsx` contêm textos reais de comentários e legendas e
ficam fora do repositório (`.gitignore`); `conferencia_topicos_sem_textos.csv` é a mesma planilha sem os textos.
