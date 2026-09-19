import pandas as pd

from src.features.silver.governors_metadata_cleaner import GovernorsMetadataCleaner


def _df_governadores(links: list) -> pd.DataFrame:
    n = len(links)
    return pd.DataFrame(
        {
            "Governador": [f"gov{i}" for i in range(n)],
            "Unidade Federativa": [f"UF{i}" for i in range(n)],
            "Partido": [f"P{i}" for i in range(n)],
            "Link": links,
        }
    )


def test_governors_metadata_cleaner_basic():
    df = _df_governadores(["https://instagram.com/a"])
    out = GovernorsMetadataCleaner().clean(df, run_id="r1")
    assert len(out) == 1
    assert out.iloc[0]["inputUrl"] == "https://instagram.com/a"


def test_governors_metadata_cleaner_descarta_governador_sem_instagram():
    """Um governador pode ficar temporariamente sem conta rastreável (ex.:
    sucessão para titular interino sem perfil público) -- a linha continua em
    governadores.xlsx com `Link` em branco/NaN, mas não pode virar o texto
    literal "nan" em `inputUrl` (NOT NULL, chave de junção do pipeline)."""
    df = _df_governadores(["https://instagram.com/a", None])
    out = GovernorsMetadataCleaner().clean(df, run_id="r1")
    assert len(out) == 1
    assert out.iloc[0]["inputUrl"] == "https://instagram.com/a"
    assert "nan" not in out["inputUrl"].tolist()
