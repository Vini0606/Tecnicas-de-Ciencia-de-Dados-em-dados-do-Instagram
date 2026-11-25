# Validação do sentimento dos comentários (Seção 5.4.1 do TCC)

Versionados: critério de anotação, identificadores, rótulos, previsões, métricas e código. **Fora do repositório**
(`.gitignore`), por conterem textos reais de comentários de terceiros: `*_para_rotular.csv`, `amostra_regra.csv` e
`*planilha_conferencia*.xlsx`. Os nomes de usuário dos comentaristas foram retirados de `gabarito_modelo.csv`.

Os textos se recuperam de quem tem acesso ao dataset privado da Coleta, pelo `id_comment` dos gabaritos e, no caso da amostra
principal e do teste, pelo sorteio com semente fixa. Os notebooks `sentimento_01_*` e `sentimento_02_*` precisam desses arquivos para
reexecutar; `robustez_por_perfil.py` (Seção 5.4.3) não precisa, lê só a Gold. Três saídas que mostravam textos foram omitidas.
