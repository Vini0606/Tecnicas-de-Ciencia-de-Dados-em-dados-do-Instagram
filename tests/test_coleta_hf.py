"""Testes da publicacao/download/listagem de Snapshots no HF (ADR 0039, issue #249).

Nunca usam a rede nem token: o cliente HF e um fake em memoria.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from src.coleta.hf import (
    ErroColetaHF,
    ErroLimiteArmazenamento,
    ErroTagExistente,
    Plano,
    baixar,
    listar,
    planejar,
    publicar,
)
from src.coleta.manifesto import validar_manifesto
from src.coleta.recorte import Recorte

TAG = "coleta_2026-10-09_ultimos-90d_teto-250"
TAG2 = "coleta_2026-10-10_teto-10"


def _manifesto(tag: str = TAG, dias: int | None = 90, teto: int | None = 250) -> dict:
    vazio = {"itens": 0, "mais_antiga": None, "mais_recente": None, "por_perfil": []}
    posts = {
        "itens": 10,
        "mais_antiga": "2026-07-12",
        "mais_recente": "2026-10-08",
        "por_perfil": [{"username": "gov_a", "itens": 10, "mais_antiga": "2026-07-12", "mais_recente": "2026-10-08"}],
    }
    m = {
        "versao_esquema": 1,
        "identidade": {"tag": tag, "extraido_em": "2026-10-09T10:00:00", "versao_codigo": "abc123"},
        "recorte": {"dias": dias, "inicio": None, "fim": None, "teto": teto},
        "cobertura": {"posts": posts, "reels": dict(vazio), "perfis": dict(vazio), "ugc": dict(vazio)},
        "custo": {"estimado": None, "real": None},
        "tabelas": [{"camada": "bronze", "nome": "instagram_posts", "linhas": 10}],
    }
    validar_manifesto(m)
    return m


def _snapshot(base: Path, arquivos: dict[str, bytes] | None = None, manifesto: dict | None = None) -> Path:
    if arquivos is None:
        arquivos = {
            "bronze/instagram_posts/_delta_log/00000000000000000000.json": b"{}",
            "bronze/instagram_posts/part-1.parquet": b"x" * 100,
            "silver/posts/part-1.parquet": b"y" * 50,
            "gold/governor_engagement/part-1.parquet": b"z" * 50,
        }
    base.mkdir(parents=True, exist_ok=True)
    for rel, conteudo in arquivos.items():
        alvo = base / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(conteudo)
    (base / "manifesto.json").write_text(json.dumps(manifesto or _manifesto()), encoding="utf-8")
    return base


class ClienteFake:
    """Repositorio em memoria: commits em `main`, tags apontando para commits."""

    def __init__(self, uso_bytes: int = 0):
        self.commits: list[dict[str, bytes]] = [{}]  # indice = id do commit
        self.tags: dict[str, int] = {}
        self.uso = uso_bytes
        self.mensagens: list[str] = []

    # --- leitura
    def listar_tags(self) -> list[str]:
        return list(self.tags)

    def listar_arquivos(self, revisao: str | None = None) -> list[str]:
        return sorted(self._arvore(revisao))

    def ler_arquivo(self, caminho: str, revisao: str | None = None) -> bytes:
        arvore = self._arvore(revisao)
        if caminho not in arvore:
            raise FileNotFoundError(caminho)
        return arvore[caminho]

    def tamanho_dataset(self) -> int:
        return self.uso

    def baixar(self, pasta: Path, revisao: str | None = None) -> None:
        for rel, conteudo in self._arvore(revisao).items():
            alvo = Path(pasta) / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(conteudo)

    # --- escrita (sem apagar tag e sem force-push: nem existem na interface)
    def commit_substituicao(self, pasta: Path, apagar: list[str], mensagem: str) -> str:
        nova = dict(self.commits[-1])
        for rel in apagar:
            nova.pop(rel, None)
        for arq in Path(pasta).rglob("*"):
            if arq.is_file():
                nova[arq.relative_to(pasta).as_posix()] = arq.read_bytes()
        self.commits.append(nova)
        self.mensagens.append(mensagem)
        return str(len(self.commits) - 1)

    def criar_tag(self, tag: str, revisao: str) -> None:
        self.tags[tag] = int(revisao)

    def _arvore(self, revisao: str | None) -> dict[str, bytes]:
        if revisao is None or revisao == "main":
            return self.commits[-1]
        if revisao in self.tags:
            return self.commits[self.tags[revisao]]
        raise FileNotFoundError(revisao)


def _sim(plano: Plano) -> bool:
    return True


def _segundo_snapshot(base: Path) -> Path:
    return _snapshot(
        base,
        {"bronze/instagram_posts/part-2.parquet": b"n", "silver/posts/part-1.parquet": b"nova"},
        _manifesto(TAG2, None, 10),
    )


# ------------------------------------------------------------------ publicar


def test_publicar_gera_um_unico_commit_de_substituicao_e_a_tag_esperada(tmp_path):
    snap = _snapshot(tmp_path / "snap")
    cliente = ClienteFake()

    resultado = publicar(snap, cliente=cliente, confirmar=_sim)

    assert len(cliente.commits) == 2  # inicial vazio + exatamente um commit
    assert len(cliente.mensagens) == 1
    assert cliente.tags == {TAG: 1}
    assert resultado.tag == TAG
    assert resultado.publicado is True
    main = cliente.listar_arquivos()
    assert "manifesto.json" in main
    assert "bronze/instagram_posts/part-1.parquet" in main
    assert "silver/posts/part-1.parquet" in main
    assert "gold/governor_engagement/part-1.parquet" in main


def test_publicar_apaga_arquivos_antigos_que_nao_existem_mais_no_snapshot(tmp_path):
    cliente = ClienteFake()
    publicar(_snapshot(tmp_path / "a"), cliente=cliente, confirmar=_sim)

    publicar(_segundo_snapshot(tmp_path / "b"), cliente=cliente, confirmar=_sim)

    assert cliente.listar_arquivos() == [
        "bronze/instagram_posts/part-2.parquet",
        "manifesto.json",
        "silver/posts/part-1.parquet",
    ]
    assert cliente.ler_arquivo("silver/posts/part-1.parquet") == b"nova"
    # a Coleta anterior continua acessivel pela tag
    assert "gold/governor_engagement/part-1.parquet" in cliente.listar_arquivos(TAG)


def test_publicar_preserva_arquivos_fora_das_camadas_da_coleta(tmp_path):
    cliente = ClienteFake()
    cliente.commits[-1]["README.md"] = b"leia-me"
    publicar(_snapshot(tmp_path / "snap"), cliente=cliente, confirmar=_sim)
    assert "README.md" in cliente.listar_arquivos()


def test_rotulo_entra_na_tag_e_no_manifesto_publicado(tmp_path):
    cliente = ClienteFake()
    resultado = publicar(_snapshot(tmp_path / "snap"), "piloto", cliente=cliente, confirmar=_sim)

    esperada = TAG + "_piloto"
    assert resultado.tag == esperada
    assert esperada in cliente.tags
    publicado = json.loads(cliente.ler_arquivo("manifesto.json"))
    assert publicado["identidade"]["tag"] == esperada


def test_rotulo_invalido_e_recusado_sem_alterar_nada(tmp_path):
    cliente = ClienteFake()
    with pytest.raises(ValueError):
        publicar(_snapshot(tmp_path / "snap"), "Piloto Ruim", cliente=cliente, confirmar=_sim)
    assert len(cliente.commits) == 1 and not cliente.tags


def test_tag_existente_e_recusada_sem_alterar_nada(tmp_path):
    cliente = ClienteFake()
    publicar(_snapshot(tmp_path / "a"), cliente=cliente, confirmar=_sim)
    antes = (list(cliente.commits), dict(cliente.tags), list(cliente.mensagens))
    chamadas: list[Plano] = []

    with pytest.raises(ErroTagExistente):
        publicar(_snapshot(tmp_path / "b"), cliente=cliente, confirmar=lambda p: chamadas.append(p) or True)

    assert (cliente.commits, cliente.tags, cliente.mensagens) == antes
    assert chamadas == []  # nem chegou a pedir confirmacao


def test_snapshot_sem_manifesto_ou_invalido_e_recusado(tmp_path):
    cliente = ClienteFake()
    snap = _snapshot(tmp_path / "snap")
    (snap / "manifesto.json").unlink()
    with pytest.raises(ErroColetaHF):
        publicar(snap, cliente=cliente, confirmar=_sim)

    (snap / "manifesto.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        publicar(snap, cliente=cliente, confirmar=_sim)
    assert len(cliente.commits) == 1


def test_interface_do_cliente_nao_oferece_apagar_tag_nem_force_push():
    from src.coleta.hf import ClienteColetaHF

    nomes = {n for n in vars(ClienteColetaHF) if not n.startswith("_")}
    assert nomes == {
        "listar_tags",
        "listar_arquivos",
        "ler_arquivo",
        "tamanho_dataset",
        "baixar",
        "commit_substituicao",
        "criar_tag",
    }


# ------------------------------------------------------------- confirmacao


def test_confirmacao_recebe_o_alvo_exato(tmp_path):
    cliente = ClienteFake()
    publicar(_snapshot(tmp_path / "a"), cliente=cliente, confirmar=_sim)
    vistos: list[Plano] = []

    publicar(_segundo_snapshot(tmp_path / "b"), cliente=cliente, confirmar=lambda p: vistos.append(p) or True)

    (plano,) = vistos
    assert plano.tag == TAG2
    assert plano.apagar == (
        "bronze/instagram_posts/_delta_log/00000000000000000000.json",
        "bronze/instagram_posts/part-1.parquet",
        "gold/governor_engagement/part-1.parquet",
    )
    assert plano.substituir == ("manifesto.json", "silver/posts/part-1.parquet")
    assert plano.adicionar == ("bronze/instagram_posts/part-2.parquet",)
    texto = plano.descrever()
    assert TAG2 in texto
    for rel in plano.apagar + plano.substituir + plano.adicionar:
        assert rel in texto


def test_sem_confirmacao_nada_e_alterado(tmp_path):
    cliente = ClienteFake()
    resultado = publicar(_snapshot(tmp_path / "snap"), cliente=cliente, confirmar=lambda p: False)

    assert resultado.publicado is False
    assert resultado.plano.tag == TAG
    assert len(cliente.commits) == 1 and not cliente.tags


def test_planejar_nao_altera_nada_e_nao_exige_confirmacao(tmp_path):
    cliente = ClienteFake()
    plano = planejar(_snapshot(tmp_path / "snap"), cliente=cliente)
    assert plano.tag == TAG
    assert len(cliente.commits) == 1


# --------------------------------------------------------------- armazenamento


def test_limite_de_armazenamento_recusa_antes_de_enviar(tmp_path):
    cliente = ClienteFake(uso_bytes=900)
    snap = _snapshot(tmp_path / "snap")  # ~200 bytes + manifesto

    with pytest.raises(ErroLimiteArmazenamento) as exc:
        publicar(snap, cliente=cliente, confirmar=_sim, limite_bytes=1000)

    assert len(cliente.commits) == 1 and not cliente.tags
    assert "1000" in str(exc.value)


def test_limite_de_armazenamento_folgado_permite_publicar(tmp_path):
    cliente = ClienteFake(uso_bytes=100)
    resultado = publicar(_snapshot(tmp_path / "snap"), cliente=cliente, confirmar=_sim, limite_bytes=10_000)
    assert resultado.publicado is True


# ------------------------------------------------------------------- listar


def test_listar_devolve_tag_recorte_e_cobertura_dos_manifestos(tmp_path):
    cliente = ClienteFake()
    publicar(_snapshot(tmp_path / "a"), cliente=cliente, confirmar=_sim)
    publicar(_segundo_snapshot(tmp_path / "b"), cliente=cliente, confirmar=_sim)
    cliente.tags["rascunho-qualquer"] = 1  # tag fora da gramatica e ignorada
    cliente.tags["coleta_2026-10-06_piloto"] = 0  # sem manifesto: ignorada

    coletas = listar(cliente=cliente)

    assert [c.tag for c in coletas] == [TAG2, TAG]  # mais recente primeiro
    antiga = coletas[1]
    assert antiga.recorte == Recorte(dias=90, teto=250)
    assert antiga.cobertura["posts"]["itens"] == 10
    assert antiga.cobertura["posts"]["por_perfil"][0]["username"] == "gov_a"
    assert antiga.extraido_em == datetime(2026, 10, 9, 10, 0, 0)
    assert coletas[0].recorte == Recorte(teto=10)


def test_listar_recorte_com_intervalo_absoluto(tmp_path):
    tag = "coleta_2026-10-09_de-2026-03-01_ate-2026-06-30_teto-50"
    m = _manifesto(tag, None, 50)
    m["recorte"]["inicio"], m["recorte"]["fim"] = "2026-03-01", "2026-06-30"
    cliente = ClienteFake()
    publicar(_snapshot(tmp_path / "a", manifesto=m), cliente=cliente, confirmar=_sim)

    (c,) = listar(cliente=cliente)
    assert c.recorte == Recorte(inicio=date(2026, 3, 1), fim=date(2026, 6, 30), teto=50)


# ------------------------------------------------------------------- baixar


def test_baixar_traz_o_snapshot_completo_da_revisao(tmp_path):
    cliente = ClienteFake()
    publicar(_snapshot(tmp_path / "a"), cliente=cliente, confirmar=_sim)
    publicar(_segundo_snapshot(tmp_path / "b"), cliente=cliente, confirmar=_sim)

    destino = tmp_path / "baixado"
    baixar(TAG, destino, cliente=cliente)

    assert (destino / "bronze/instagram_posts/part-1.parquet").read_bytes() == b"x" * 100
    assert (destino / "silver/posts/part-1.parquet").read_bytes() == b"y" * 50
    assert (destino / "gold/governor_engagement/part-1.parquet").exists()
    assert not (destino / "bronze/instagram_posts/part-2.parquet").exists()  # arquivo da Coleta nova
    manifesto = json.loads((destino / "manifesto.json").read_text(encoding="utf-8"))
    validar_manifesto(manifesto)
    assert manifesto["identidade"]["tag"] == TAG


def test_baixar_tag_inexistente_levanta_erro_claro(tmp_path):
    with pytest.raises(ErroColetaHF):
        baixar("coleta_2026-01-01_teto-1", tmp_path / "x", cliente=ClienteFake())


def test_baixar_recusa_tag_fora_da_gramatica(tmp_path):
    with pytest.raises(ValueError):
        baixar("main", tmp_path / "x", cliente=ClienteFake())
