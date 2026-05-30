import json
from pathlib import Path

import pandas as pd


class JsonDataReader:
    """
    Responsabilidade única: ler arquivos JSON do disco e retornar DataFrames.
    Não sabe nada sobre a API, transformações ou persistência.
    """

    def read(self, path: Path) -> pd.DataFrame:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Arquivo não encontrado: {path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON inválido em {path}: {e}")
        return pd.DataFrame(data)

    def save(self, data: list[dict], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
