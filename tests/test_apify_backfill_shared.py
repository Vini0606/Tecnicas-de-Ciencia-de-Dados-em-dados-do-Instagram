import pandas as pd

from config import settings
from scripts.apify_backfill_shared import (
    RESULTS_LIMIT_FLOOR,
    RESULTS_LIMIT_SAFETY_MARGIN_PER_DAY,
    default_results_limit,
    estimate_cost_usd,
    load_links,
    profiles_hitting_limit,
    project_backfill_costs,
)


def test_default_results_limit_usa_o_piso_para_janelas_curtas():
    assert default_results_limit(1) == RESULTS_LIMIT_FLOOR


def test_default_results_limit_escala_com_days():
    dias = 365
    assert default_results_limit(dias) == dias * RESULTS_LIMIT_SAFETY_MARGIN_PER_DAY


def test_profiles_hitting_limit_identifica_perfis_truncados():
    items = [
        {"inputUrl": "https://instagram.com/a"},
        {"inputUrl": "https://instagram.com/a"},
        {"inputUrl": "https://instagram.com/b"},
    ]
    assert profiles_hitting_limit(items, results_limit=2) == ["https://instagram.com/a"]


def test_profiles_hitting_limit_sem_truncagem():
    items = [{"inputUrl": "https://instagram.com/a"}]
    assert profiles_hitting_limit(items, results_limit=10) == []


def test_estimate_cost_usd_e_positivo_e_cresce_com_days():
    custo_curto = estimate_cost_usd(days=30, n_governors=27)
    custo_longo = estimate_cost_usd(days=90, n_governors=27)
    assert custo_curto > 0
    assert custo_longo > custo_curto


def test_project_backfill_costs_retorna_as_quatro_janelas():
    projections = project_backfill_costs(total_results=1000, days=90)
    assert set(projections.keys()) == {1, 2, 3, 4}
    assert projections[1] < projections[4]


def test_load_links_le_e_normaliza_planilha(monkeypatch):
    df_fake = pd.DataFrame(
        {f" {settings.LINK_COLUMN} ": [" https://instagram.com/a ", " https://instagram.com/a "]}
    )
    monkeypatch.setattr("scripts.apify_backfill_shared.pd.read_excel", lambda *a, **k: df_fake)

    links = load_links()

    assert links == ["https://instagram.com/a"]
