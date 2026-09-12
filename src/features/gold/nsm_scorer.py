"""
North Star Metric (NSM) de engajamento qualificado por perfil (ADR 0020,
Ficha 5 / issue #90).

O engajamento bruto (curtidas+comentários) não distingue engajamento de
QUALIDADE (reação positiva do público) de engajamento de VOLUME puro -- um
post com muitos comentários negativos rankeia igual a um com muitos
comentários positivos. O NSM qualifica o engajamento combinando duas fontes
que já existem em `main` mas nunca foram cruzadas: `governor_sentiment`
(sentimento de COMENTÁRIO, ADR 0019/0020 Ficha 3, issue #88) e
`governor_engagement` (agregado de engajamento por perfil, ADR 0018).

Estágio pós-modelagem, mesma posição/dependência do Score ICE (ADR 0020
Ficha 6 / issue #91, ver `TopicPriorityScorer`) -- 100% automatizado, sem
input humano, e não força o `EngagementAggregator` original a depender de
sentimento (que inverteria a ordem do pipeline: engajamento roda ANTES da
modelagem).

Fórmula (fixa pela ADR 0020, não reaberta aqui):

    NSM = (comentários positivos / comentários totais) x alcance médio

- **comentários positivos / comentários totais**: só comentários (`fonte ==
  "comentario"` quando a coluna existe -- `governor_sentiment` também
  acumula linha de legenda/transcrição, que não deve contar aqui; mesmo
  filtro de escopo do Score ICE, ver `TopicPriorityScorer`), agregado por
  perfil (`inputUrl`).
- **alcance médio -- PROXY explícito, não alcance real**: Instagram não
  expõe alcance/views real para posts estáticos, e `governor_engagement`
  (Gold, ADR 0018) não guarda nenhuma coluna de alcance -- só
  `likesSum`/`commentsSum`/`TOTAL ENGAJAMENTO`/`count`. O proxy escolhido é
  `TOTAL ENGAJAMENTO / count` (engajamento médio por post) -- mede
  INTENSIDADE de engajamento por publicação, não alcance/impressões. Mesmo
  raciocínio de proxy documentado já usado pelo Score ICE (Ficha 6) para
  "alcance do tópico" (soma de likes+replies do comentário). Esta é uma
  limitação metodológica a declarar sempre que o NSM for consumido
  (dashboard, Cap. 6/7 do TCC), não escondida atrás do nome "alcance".

Junção por `inputUrl` -- mesma chave de perfil já usada por
`src.modeling.growth_history` (`GROUP_COL_DEFAULT`) e por
`GOLD_POST_PERFORMANCE_PREDICTIONS_SCHEMA`. `governor_sentiment` grava
`inputUrl` por linha (propagado da Silver de comentários,
`SILVER_COMMENTS_SCHEMA`); `governor_engagement` grava `inputUrl` por
perfil (`EngagementAggregator`).

Convenções de "não calculável" -- nunca `ZeroDivisionError` nem `NaN`
propagado, mesmo raciocínio de resultado sempre definido já usado pelo
Score ICE:
- perfil com 0 comentários (nenhuma linha em `governor_sentiment` para o
  `inputUrl`, ou 0 depois do filtro de fonte): `proporcao_positivos = 0.0`
  -- "sem engajamento qualificado observado" é uma leitura de negócio
  válida, não uma ausência a esconder atrás de `NaN`.
- perfil com 0 posts (`count == 0` em `governor_engagement`):
  `alcance_medio = 0.0`.

O merge entre as duas fontes é `outer`: um perfil pode existir em só uma
das duas tabelas (ex.: engajamento já agregado mas sentimento de comentário
ainda não recalculado para aquele perfil na execução atual) -- o lado
ausente entra com 0 em vez de sumir do ranking (mesmo raciocínio de
`compute_growth_metrics`, ADR 0020 Ficha 7 / issue #92).

*** VERIFICAÇÃO COM DADO REAL (critério de aceite da ADR/Ficha 5 para o Cap.
6, issue #90) -- PENDENTE, declarar explicitamente enquanto isso for
verdade ***
A issue pede rodar o NSM sobre os 27 perfis reais e confirmar pelo menos 1
caso onde a posição no ranking muda entre NSM e engajamento bruto. Este
ambiente de desenvolvimento não tem Delta real em `data/gold/` (a árvore é
efêmera/gitignored, ver ADR 0013 -- só `.gitkeep` nos diretórios existentes,
sem linhas). A prova de inversão de ranking pedida pela issue está coberta
aqui só com dado SINTÉTICO (ver
`TestRankingContrastaComEngajamentoBruto.test_ranking_por_nsm_inverte_ranking_por_engajamento_bruto`
em `tests/test_nsm_scorer.py`), que valida a fórmula/lógica de inversão, não
o resultado sobre os 27 perfis reais. Mesmo raciocínio de "ilustrativo até
dado real acumular" já usado pelo CMGR (ADR 0020 Ficha 7 / issue #92, ver
`src/modeling/growth_history.py`): quem rodar `run_deterministic_modeling`
contra a Gold real (`scripts/run_modeling.py`) deve inspecionar
`governor_nsm` resultante e confirmar o critério de aceite com dado real
antes de declarar o Cap. 6 do TCC fechado nesse ponto -- este módulo não
pode fazer essa verificação sozinho, sem execução real do pipeline.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.delta_io import write_delta
from src.schemas_delta import GOLD_NSM_SCHEMA

_RESULT_COLUMNS = [
    "inputUrl",
    "username",
    "n_comentarios_positivos",
    "n_comentarios_totais",
    "proporcao_positivos",
    "total_engajamento",
    "count_posts",
    "alcance_medio",
    "nsm",
]

_POSITIVIDADE_COLUMNS = ["inputUrl", "n_comentarios_positivos", "n_comentarios_totais"]


class NsmScorer:
    def score(self, df_sentiment: pd.DataFrame, df_engagement: pd.DataFrame) -> pd.DataFrame:
        """Calcula o NSM por perfil. `df_sentiment` é `governor_sentiment`
        (uma linha por comentário/legenda/transcrição avaliado);
        `df_engagement` é `governor_engagement` (uma linha por perfil). Uma
        linha de saída por perfil (`inputUrl`), ordenada por `nsm`
        decrescente (ranking pronto para consumo, mesmo padrão de
        `TopicPriorityScorer.score`)."""
        required_sentiment = {"inputUrl", "sentiment_label"}
        missing = required_sentiment - set(df_sentiment.columns)
        if missing:
            raise ValueError(
                f"df_sentiment não tem as colunas esperadas: {sorted(missing)}"
            )
        required_engagement = {"inputUrl", "TOTAL ENGAJAMENTO", "count"}
        missing = required_engagement - set(df_engagement.columns)
        if missing:
            raise ValueError(
                f"df_engagement não tem as colunas esperadas: {sorted(missing)}"
            )

        df_sent = df_sentiment.copy()
        # NSM é só sobre comentário -- mesmo filtro de escopo do Score ICE
        # (`TopicPriorityScorer`): `governor_sentiment` também acumula
        # legenda/transcrição (issue #88), que não é "comentário" nenhum.
        # `fonte` é opcional aqui pelo mesmo motivo do Score ICE (dado
        # sintético de teste, ou uma tabela futura sem a coluna, não quebra).
        if "fonte" in df_sent.columns:
            df_sent = df_sent[df_sent["fonte"] == "comentario"]
        df_sent = df_sent.dropna(subset=["inputUrl"])

        if df_sent.empty:
            df_positividade = pd.DataFrame(columns=_POSITIVIDADE_COLUMNS)
        else:
            positivo = df_sent["sentiment_label"].astype(str).str.lower() == "positive"
            df_positividade = (
                df_sent.assign(_positivo=positivo)
                .groupby("inputUrl", dropna=False)
                .agg(
                    n_comentarios_positivos=("_positivo", "sum"),
                    n_comentarios_totais=("_positivo", "size"),
                )
                .reset_index()
            )

        df_eng = df_engagement.dropna(subset=["inputUrl"]).copy()
        df_eng = df_eng.rename(
            columns={"TOTAL ENGAJAMENTO": "total_engajamento", "count": "count_posts"}
        )
        colunas_engagement = ["inputUrl", "total_engajamento", "count_posts"]
        if "username" in df_eng.columns:
            colunas_engagement.append("username")
        df_eng = df_eng[colunas_engagement]

        combined = pd.merge(df_eng, df_positividade, on="inputUrl", how="outer")

        if "username" not in combined.columns:
            combined["username"] = pd.NA

        for coluna in ("n_comentarios_positivos", "n_comentarios_totais"):
            combined[coluna] = (
                pd.to_numeric(combined[coluna], errors="coerce").fillna(0).astype("int64")
            )
        for coluna in ("total_engajamento", "count_posts"):
            combined[coluna] = (
                pd.to_numeric(combined[coluna], errors="coerce").fillna(0).astype("int64")
            )

        # `.where(x > 0)` deixa a divisão indefinida virar NaN em vez de
        # ZeroDivisionError/inf; o `.fillna(0.0)` seguinte resolve os dois
        # casos de "não calculável" documentados na docstring do módulo
        # (0 comentários / 0 posts) para um valor sempre definido.
        n_totais = combined["n_comentarios_totais"]
        combined["proporcao_positivos"] = (
            combined["n_comentarios_positivos"].div(n_totais.where(n_totais > 0)).fillna(0.0)
        )
        n_posts = combined["count_posts"]
        combined["alcance_medio"] = (
            combined["total_engajamento"].div(n_posts.where(n_posts > 0)).fillna(0.0)
        )
        combined["nsm"] = combined["proporcao_positivos"] * combined["alcance_medio"]

        return (
            combined[_RESULT_COLUMNS]
            .sort_values(["nsm", "inputUrl"], ascending=[False, True])
            .reset_index(drop=True)
        )

    def write(
        self,
        df_scored: pd.DataFrame,
        path: Path | str,
        run_id: str,
        mode: str = "overwrite",
        generated_at: datetime | None = None,
    ) -> None:
        """Grava `governor_nsm` -- uma linha por perfil, saída de `score()`.
        `generated_at` explícito opcional, mesmo padrão de
        `TopicPriorityScorer.write`/`ModelEnricher.write_sentiment`, para
        carimbar o mesmo timestamp de outras tabelas escritas no mesmo
        `run_id`."""
        df = df_scored.copy()
        df["_run_id"] = run_id
        df["_generated_at"] = generated_at or datetime.now(timezone.utc)
        write_delta(path, df, GOLD_NSM_SCHEMA, mode=mode)
