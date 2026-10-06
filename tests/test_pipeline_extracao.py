"""Issue #213: janela de datas, teto por perfil e extração forçada no
pipeline.py -- funções puras de resolução de parâmetros, custo e CLI."""

from datetime import datetime

import pandas as pd
import pytest

from config import settings


def test_resolver_extracao_sem_flags_usa_teto_padrao_e_nao_forca():
    from pipeline import resolver_extracao

    params = resolver_extracao()

    assert params.force_extract is False
    assert params.results_limit == settings.RESULTS_LIMIT
    assert params.days is None
    assert params.extra_run_input is None


def test_resolver_extracao_so_force_extract():
    from pipeline import resolver_extracao

    params = resolver_extracao(force_extract=True)

    assert params.force_extract is True
    assert params.results_limit == settings.RESULTS_LIMIT
    assert params.extra_run_input is None


def test_resolver_extracao_days_sem_teto_usa_padrao_por_janela_e_forca_extracao():
    """`--days` implica extração real (senão a Bronze em cache faria a janela
    ser ignorada em silêncio) e, sem `--results-limit`, usa o mesmo padrão do
    backfill: max(200, 10 x dias)."""
    from pipeline import resolver_extracao

    params = resolver_extracao(days=150)

    assert params.force_extract is True
    assert params.results_limit == 1500
    assert params.extra_run_input == {"onlyPostsNewerThan": "150 days"}


def test_resolver_extracao_days_curto_respeita_piso_do_teto():
    from pipeline import resolver_extracao

    assert resolver_extracao(days=5).results_limit == 200


def test_resolver_extracao_teto_explicito_prevalece_sobre_o_padrao_da_janela():
    from pipeline import resolver_extracao

    params = resolver_extracao(days=150, results_limit=400)

    assert params.results_limit == 400
    assert params.extra_run_input == {"onlyPostsNewerThan": "150 days"}


def test_resolver_extracao_teto_sem_janela_nao_forca_extracao():
    from pipeline import resolver_extracao

    params = resolver_extracao(results_limit=80)

    assert params.results_limit == 80
    assert params.force_extract is False
    assert params.extra_run_input is None


def test_estimar_custo_sem_janela_cobra_as_tres_colecoes_pelo_teto():
    # 26 governadores x 30 por coleção a US$ 2,30 por mil resultados:
    # posts+reels = 1560 -> 3.59; UGC = 780 -> 1.79; as três = 2340 -> 5.38.
    from pipeline import estimar_custo

    custo = estimar_custo(days=None, results_limit=30, n_governors=26)

    assert custo == {"posts_reels": 3.59, "ugc": 1.79, "total": 5.38}


def test_estimar_custo_com_janela_usa_taxa_calibrada_para_posts_e_reels():
    # posts+reels: (1.65 + 2.60) x 10 dias x 26 = 1105 resultados -> 2.54;
    # UGC: pior caso pelo teto, 26 x 200 = 5200 -> 11.96; total 14.50.
    from pipeline import estimar_custo

    custo = estimar_custo(days=10, results_limit=200, n_governors=26)

    assert custo == {"posts_reels": 2.54, "ugc": 11.96, "total": 14.5}


@pytest.mark.parametrize("valor", ["0", "-3", "abc"])
def test_cli_rejeita_days_e_results_limit_nao_positivos(valor):
    from pipeline import build_arg_parser

    parser = build_arg_parser()
    for flag in ("--days", "--results-limit"):
        with pytest.raises(SystemExit):
            parser.parse_args([flag, valor])


def test_cli_aceita_as_flags_novas():
    from pipeline import build_arg_parser

    args = build_arg_parser().parse_args(
        ["--days", "150", "--results-limit", "400", "--force-extract", "--yes"]
    )

    assert (args.days, args.results_limit, args.force_extract, args.yes) == (150, 400, True, True)


def test_filtrar_ugc_por_janela_descarta_posts_mais_antigos_que_n_dias():
    from pipeline import filtrar_ugc_por_janela

    df = pd.DataFrame(
        {
            "id": ["antigo", "limite", "recente"],
            "data_hora": pd.to_datetime(["2026-06-01", "2026-09-06", "2026-10-01"]),
        }
    )

    out = filtrar_ugc_por_janela(df, days=30, agora=datetime(2026, 10, 6))

    assert list(out["id"]) == ["limite", "recente"]


def test_filtrar_ugc_por_janela_sem_days_nao_altera_nada():
    from pipeline import filtrar_ugc_por_janela

    df = pd.DataFrame({"id": ["a"], "data_hora": pd.to_datetime(["2013-01-01"])})

    out = filtrar_ugc_por_janela(df, days=None, agora=datetime(2026, 10, 6))

    assert list(out["id"]) == ["a"]
