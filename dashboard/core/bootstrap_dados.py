"""Garante os dados do dashboard no disco antes de qualquer tela ler uma tabela.

No Streamlit Community Cloud o clone do repositório chega sem `data/` (que não
vai para o git). Se `HF_TOKEN` e o dataset (`HF_DATASET_REPO_PUBLICACAO` ou, na
falta dele, `HF_DATASET_REPO`) estiverem nos Secrets (ou no `.env`,
localmente), baixa Silver + Gold do dataset privado (ADR 0036). Sem configuração, não faz nada: as telas mostram o aviso
de dados ausentes de sempre.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

import streamlit as st

from config import settings
from src.publicacao_hf import ConfigHF, configuracao_hf, garantir_dados


def _secrets() -> Mapping[str, object]:
    """`st.secrets` como mapa, ou vazio quando não há `secrets.toml` (local)."""
    try:
        return {k: st.secrets[k] for k in st.secrets}
    except Exception:  # noqa: BLE001 - sem secrets configurados
        return {}


def configuracao_atual() -> ConfigHF | None:
    return configuracao_hf(os.environ, _secrets())


@st.cache_resource(show_spinner="Baixando os dados do dashboard...")
def preparar_dados(data_dir: str) -> str:
    """Uma vez por processo. Estado: `local`, `baixado`, `sem_configuracao` ou
    `erro: <motivo>` (nunca contém o token)."""
    return garantir_dados(data_dir, configuracao_atual())


def avisar_se_falhou() -> None:
    """Chamar no topo do app: baixa se preciso e mostra erro se o download falhar."""
    estado = preparar_dados(str(settings.DATA_DIR))
    if estado.startswith("erro"):
        st.error(
            "Não consegui baixar os dados do dashboard do Hugging Face. "
            f"Detalhe: {estado}"
        )
