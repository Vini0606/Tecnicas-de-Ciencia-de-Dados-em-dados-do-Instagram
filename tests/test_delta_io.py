import pandas as pd
import pyarrow as pa
import pytest
from deltalake import DeltaTable

from src.delta_io import conform_to_schema, write_delta

SCHEMA = pa.schema(
    [
        pa.field("id", pa.string(), nullable=False),
        pa.field("valor", pa.int64(), nullable=True),
    ]
)


def test_conform_descarta_colunas_fora_do_schema():
    df = pd.DataFrame({"id": ["1"], "valor": [10], "extra": ["ignorar"]})
    table = conform_to_schema(df, SCHEMA)
    assert table.column_names == ["id", "valor"]


def test_conform_cria_coluna_anulavel_ausente():
    df = pd.DataFrame({"id": ["1"]})
    table = conform_to_schema(df, SCHEMA)
    assert table.column("valor").null_count == 1


def test_conform_falha_quando_campo_obrigatorio_esta_ausente():
    """O contrato de schema precisa falhar cedo, não gravar dado incompleto."""
    df = pd.DataFrame({"valor": [10]})
    with pytest.raises(ValueError, match="non-nullable"):
        conform_to_schema(df, SCHEMA)


def test_write_delta_grava_e_le(tmp_path):
    path = tmp_path / "tabela"
    write_delta(path, pd.DataFrame({"id": ["1"], "valor": [10]}), SCHEMA)
    out = DeltaTable(str(path)).to_pandas()
    assert len(out) == 1
    assert out.loc[0, "id"] == "1"


def test_write_delta_append_acumula(tmp_path):
    path = tmp_path / "tabela"
    write_delta(path, pd.DataFrame({"id": ["1"], "valor": [1]}), SCHEMA, mode="append")
    write_delta(path, pd.DataFrame({"id": ["2"], "valor": [2]}), SCHEMA, mode="append")
    assert len(DeltaTable(str(path)).to_pandas()) == 2
