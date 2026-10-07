"""Issue #232: sincronização de landing + Bronze com o dataset privado do HF."""

import fnmatch
import importlib.util
import shutil
from pathlib import Path

import pytest

from src.dados_hf import (
    ClienteHFReal,
    ErroHF,
    inventario_de_caminhos,
    mensagem_de_commit,
    planejar_pull,
    planejar_push,
)

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("sync_dados_hf", ROOT / "scripts" / "sync_dados_hf.py")
sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync)

TOKEN = "hf_segredo_super_secreto"


def _log(versao: int) -> str:
    return f"{versao:020d}.json"


def _escrever(base: Path, relativo: str, conteudo: str = "x") -> None:
    caminho = base / relativo
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo)


def _bronze(base: Path, tabela: str, versoes: int, marca: str = "") -> None:
    for v in range(versoes):
        _escrever(base, f"bronze/{tabela}/_delta_log/{_log(v)}", marca)
    _escrever(base, f"bronze/{tabela}/part-0.parquet")


class ClienteFalso:
    """Dataset do HF simulado num diretório; respeita allow_patterns."""

    def __init__(self, raiz: Path):
        self.raiz = raiz
        raiz.mkdir(parents=True, exist_ok=True)
        self.commits: list[str] = []
        self.revisoes: list[str | None] = []

    def listar_arquivos(self, revisao=None):
        self.revisoes.append(revisao)
        return [p.relative_to(self.raiz).as_posix() for p in self.raiz.rglob("*") if p.is_file()]

    def _copiar(self, origem: Path, destino: Path, padroes):
        for arq in origem.rglob("*"):
            rel = arq.relative_to(origem).as_posix()
            if arq.is_file() and any(fnmatch.fnmatch(rel, p) for p in padroes):
                alvo = destino / rel
                alvo.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(arq, alvo)

    def enviar(self, pasta, padroes, mensagem):
        self.commits.append(mensagem)
        self._copiar(pasta, self.raiz, padroes)

    def baixar(self, pasta, padroes, revisao=None):
        self.revisoes.append(revisao)
        self._copiar(self.raiz, pasta, padroes)


@pytest.fixture
def ambiente(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    cliente = ClienteFalso(tmp_path / "hf")
    return data, cliente


def _rodar(args, data, cliente, capsys):
    codigo = sync.main(args, cliente_factory=lambda env: cliente, env={}, data_dir=data)
    return codigo, capsys.readouterr()


# ---------- lógica pura ----------

def test_push_sobe_so_landing_nova():
    local = inventario_de_caminhos(["landing/a/1.json", "landing/b/1.json"])
    remoto = inventario_de_caminhos(["landing/a/1.json"])
    plano = planejar_push(local, remoto)
    assert plano.landing == ("b",) and plano.bronze == () and plano.recusa is None


def test_push_bronze_local_a_frente_sobe():
    local = inventario_de_caminhos(
        [f"bronze/t/_delta_log/{_log(0)}", f"bronze/t/_delta_log/{_log(1)}"]
    )
    remoto = inventario_de_caminhos([f"bronze/t/_delta_log/{_log(0)}"])
    plano = planejar_push(local, remoto)
    assert plano.bronze == ("t",) and plano.versoes_bronze == {"t": 1}


def test_push_recusa_bronze_remota_a_frente():
    local = inventario_de_caminhos([f"bronze/t/_delta_log/{_log(0)}"])
    remoto = inventario_de_caminhos(
        [f"bronze/t/_delta_log/{_log(0)}", f"bronze/t/_delta_log/{_log(1)}"]
    )
    plano = planejar_push(local, remoto)
    assert plano.recusa and "pull" in plano.recusa


def test_push_recusa_bronze_divergente():
    local = inventario_de_caminhos([f"bronze/t/_delta_log/{_log(0)}", f"bronze/t/_delta_log/{_log(2)}"])
    remoto = inventario_de_caminhos([f"bronze/t/_delta_log/{_log(0)}", f"bronze/t/_delta_log/{_log(1)}"])
    plano = planejar_push(local, remoto)
    assert plano.recusa and "divergiu" in plano.recusa


def test_push_vazio_sem_novidade():
    inv = inventario_de_caminhos(["landing/a/1.json", f"bronze/t/_delta_log/{_log(0)}"])
    assert planejar_push(inv, inv).vazio


def test_pull_recusa_landing_local_nao_enviada():
    local = inventario_de_caminhos(["landing/a/1.json"])
    remoto = inventario_de_caminhos(["landing/b/1.json"])
    assert planejar_pull(local, remoto).recusa
    assert planejar_pull(local, remoto, force=True).recusa is None


def test_pull_recusa_bronze_local_a_frente():
    local = inventario_de_caminhos([f"bronze/t/_delta_log/{_log(0)}", f"bronze/t/_delta_log/{_log(1)}"])
    remoto = inventario_de_caminhos([f"bronze/t/_delta_log/{_log(0)}"])
    assert planejar_pull(local, remoto).recusa
    assert planejar_pull(local, remoto, force=True).recusa is None


def test_mensagem_cita_run_ids_e_versoes():
    local = inventario_de_caminhos(["landing/20261006_a/1.json", f"bronze/posts/_delta_log/{_log(3)}"])
    msg = mensagem_de_commit(planejar_push(local, inventario_de_caminhos([])))
    assert "20261006_a" in msg and "posts@v3" in msg


# ---------- CLI com cliente falso ----------

def test_cli_push_sem_yes_so_mostra_plano(ambiente, capsys):
    data, cliente = ambiente
    _escrever(data, "landing/r1/1.json")
    codigo, saida = _rodar(["push"], data, cliente, capsys)
    assert codigo == 0 and "r1" in saida.out
    assert cliente.commits == [] and not any(cliente.raiz.rglob("*.json"))


def test_cli_push_com_yes_envia_em_um_commit(ambiente, capsys):
    data, cliente = ambiente
    _escrever(data, "landing/r1/1.json")
    _bronze(data, "t", 2)
    _escrever(data, "silver/x/p.parquet")
    codigo, _ = _rodar(["push", "--yes"], data, cliente, capsys)
    assert codigo == 0 and len(cliente.commits) == 1 and "r1" in cliente.commits[0]
    assert (cliente.raiz / "landing/r1/1.json").exists()
    assert not (cliente.raiz / "silver").exists()


def test_cli_push_recusado_sai_com_1(ambiente, capsys):
    data, cliente = ambiente
    _bronze(cliente.raiz, "t", 2)
    _bronze(data, "t", 1)
    codigo, saida = _rodar(["push", "--yes"], data, cliente, capsys)
    assert codigo == 1 and "pull" in saida.out and cliente.commits == []


def test_cli_pull_maquina_vazia_baixa_tudo(ambiente, capsys):
    data, cliente = ambiente
    _escrever(cliente.raiz, "landing/r1/1.json")
    _bronze(cliente.raiz, "t", 2)
    codigo, _ = _rodar(["pull"], data, cliente, capsys)
    assert codigo == 0
    assert (data / "landing/r1/1.json").exists()
    assert (data / f"bronze/t/_delta_log/{_log(1)}").exists()


def test_cli_pull_nao_toca_outras_camadas(ambiente, capsys):
    data, cliente = ambiente
    _escrever(cliente.raiz, "landing/r1/1.json")
    _escrever(cliente.raiz, "silver/x/p.parquet", "remoto")
    _escrever(data, "silver/x/p.parquet", "local")
    _escrever(data, "gold/g.parquet", "local")
    _escrever(data, "logs/l.log", "local")
    _rodar(["pull"], data, cliente, capsys)
    assert (data / "silver/x/p.parquet").read_text() == "local"
    assert (data / "gold/g.parquet").exists() and (data / "logs/l.log").exists()


def test_cli_pull_recusa_dado_local_e_force_sobrescreve(ambiente, capsys):
    data, cliente = ambiente
    _escrever(cliente.raiz, "landing/r1/1.json", "remoto")
    _escrever(data, "landing/r2/1.json", "local")
    codigo, _ = _rodar(["pull"], data, cliente, capsys)
    assert codigo == 1 and not (data / "landing/r1").exists()
    codigo, _ = _rodar(["pull", "--force"], data, cliente, capsys)
    assert codigo == 0 and (data / "landing/r1/1.json").read_text() == "remoto"


def test_cli_pull_repassa_revisao(ambiente, capsys):
    data, cliente = ambiente
    _escrever(cliente.raiz, "landing/r1/1.json")
    _rodar(["pull", "--revisao", "abc123"], data, cliente, capsys)
    assert cliente.revisoes == ["abc123", "abc123"]


def test_cli_sem_credenciais_erro_claro(tmp_path, capsys):
    codigo = sync.main(["pull"], env={}, data_dir=tmp_path)
    err = capsys.readouterr().err
    assert codigo == 1 and "HF_TOKEN" in err and "HF_DATASET_REPO" in err


# ---------- token nunca vaza ----------

def test_erro_do_cliente_real_nao_vaza_token(monkeypatch):
    import huggingface_hub

    class ApiQuebrada:
        def __init__(self, token=None):
            pass

        def list_repo_files(self, *a, **k):
            raise RuntimeError(f"401 Unauthorized: Bearer {TOKEN}")

    monkeypatch.setattr(huggingface_hub, "HfApi", ApiQuebrada)
    cliente = ClienteHFReal("u/d", TOKEN)
    with pytest.raises(ErroHF) as exc:
        cliente.listar_arquivos()
    assert TOKEN not in str(exc.value) and TOKEN not in repr(exc.value.__cause__)


def test_cli_nao_imprime_token_em_falha(tmp_path, capsys, monkeypatch):
    import huggingface_hub

    class ApiQuebrada:
        def __init__(self, token=None):
            pass

        def list_repo_files(self, *a, **k):
            raise RuntimeError(f"falhou com {TOKEN}")

    monkeypatch.setattr(huggingface_hub, "HfApi", ApiQuebrada)
    codigo = sync.main(["pull"], env={"HF_TOKEN": TOKEN, "HF_DATASET_REPO": "u/d"}, data_dir=tmp_path)
    saida = capsys.readouterr()
    assert codigo == 1 and TOKEN not in saida.out and TOKEN not in saida.err
