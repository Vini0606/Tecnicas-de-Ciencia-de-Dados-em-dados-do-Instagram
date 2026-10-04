"""Testes da analise de clusters de reels (issue #189) -- so as funcoes puras de
`dashboard/screens/comparar_clusters.py`, nunca a renderizacao Streamlit."""

import pandas as pd

from dashboard.screens import comparar
from dashboard.screens import comparar_clusters as cc

GOV_A = "https://www.instagram.com/governador_a/"
GOV_B = "https://www.instagram.com/governador_b/"


def _clusters(rotulos: dict[str, int], tipo: str = "reel") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id_reel": list(rotulos),
            "cluster_label": list(rotulos.values()),
            "content_type": tipo,
        }
    )


def _reels(linhas: list[tuple]) -> pd.DataFrame:
    # (id, inputUrl, duracao, likes, comentarios, views)
    return pd.DataFrame(
        linhas,
        columns=["id", "inputUrl", "videoDuration", "likesCount", "commentsCount", "videoPlayCount"],
    )


def _base_exemplo() -> pd.DataFrame:
    # cluster 0: 6 reels (A); cluster 1: 2 reels (B); engajamento do 1 >> do 0
    clusters = _clusters({"r1": 0, "r2": 0, "r3": 0, "r4": 0, "r5": 0, "r6": 0, "r7": 1, "r8": 1})
    reels = _reels(
        [
            ("r1", GOV_A, 30, 10, 0, 100),
            ("r2", GOV_A, 30, 10, 0, 100),
            ("r3", GOV_A, 30, 10, 0, 100),
            ("r4", GOV_B, 30, 10, 0, 100),
            ("r5", GOV_B, 30, 10, 0, 100),
            ("r6", GOV_B, 30, 10, 0, 100),
            ("r7", GOV_A, 120, 100, 20, 900),
            ("r8", GOV_B, 120, 100, 20, 900),
        ]
    )
    return cc.montar_base_reels(clusters, reels)


# --- base ------------------------------------------------------------------


def test_base_filtra_content_type_reel():
    clusters = pd.concat([_clusters({"r1": 0}), _clusters({"p1": 0}, tipo="feed")])
    base = cc.montar_base_reels(clusters, _reels([("r1", GOV_A, 30, 1, 2, 3)]))
    assert base["id_reel"].tolist() == ["r1"]
    assert base["engajamento"].iloc[0] == 3


def test_base_tabela_de_clusters_vazia():
    base = cc.montar_base_reels(pd.DataFrame(), _reels([("r1", GOV_A, 30, 1, 2, 3)]))
    assert base.empty
    assert cc.ordenar_clusters(base) == []
    assert cc.medianas_globais(base) == {"duracao": None, "engajamento": None}
    assert cc.composicao_sentimento(pd.DataFrame(), base, None) is None


def test_base_reel_sem_silver_permanece_com_metricas_nan():
    base = cc.montar_base_reels(_clusters({"r1": 0, "rX": 0}), _reels([("r1", GOV_A, 30, 1, 2, 3)]))
    assert len(base) == 2
    assert cc.metricas_cluster(base, 0)["n_reels"] == 2
    assert cc.metricas_cluster(base, 0)["likes_media"] == 1


# --- ordem / rotulos --------------------------------------------------------


def test_ordem_por_tamanho_e_numeracao_ignora_ruido():
    clusters = _clusters({"a": 5, "b": 5, "c": 5, "d": 7, "e": -1, "f": -1})
    base = cc.montar_base_reels(clusters, pd.DataFrame())
    ordem = cc.ordenar_clusters(base)
    assert ordem == [5, -1, 7]  # tamanho desc; empate pelo id menor
    assert cc.numero_cluster(5, ordem) == "Cluster 1"
    assert cc.numero_cluster(7, ordem) == "Cluster 2"


def test_ruido_vira_casos_atipicos_nunca_menos_um():
    ordem = [0, -1]
    rotulo = cc.rotulo_botao(-1, ordem, "qualquer")
    assert rotulo == "Casos atípicos / virais"
    assert "-1" not in rotulo
    assert cc.nome_cluster(-1, {"duracao_mediana": 1, "engajamento_mediano": 1}, {"duracao": 1, "engajamento": 1}) == (
        "Casos atípicos / virais"
    )


# --- metricas / medianas -----------------------------------------------------


def test_metricas_do_cluster_e_mediana_global():
    base = _base_exemplo()
    m0 = cc.metricas_cluster(base, 0)
    assert m0["n_reels"] == 6
    assert m0["duracao_media"] == 30
    assert m0["likes_media"] == 10
    m1 = cc.metricas_cluster(base, 1)
    assert m1["n_reels"] == 2
    assert m1["views_media"] == 900
    assert m1["engajamento_mediano"] == 120
    globais = cc.medianas_globais(base)
    assert globais["duracao"] == 30  # mediana dos 8: seis 30 e dois 120
    assert globais["engajamento"] == 10


def test_fmt_duracao():
    assert cc.fmt_duracao(None) == ("—", "")
    assert cc.fmt_duracao(90) == ("90 s", "~2 min")
    assert cc.fmt_duracao(20) == ("20 s", "menos de 1 min")


# --- regras ------------------------------------------------------------------


def test_nivel_relativo_limiares():
    assert cc.nivel_relativo(100, 100) == 0
    assert cc.nivel_relativo(120, 100) == 1
    assert cc.nivel_relativo(150, 100) == 2
    assert cc.nivel_relativo(80, 100) == -1
    assert cc.nivel_relativo(50, 100) == -2
    assert cc.nivel_relativo(None, 100) is None
    assert cc.nivel_relativo(10, 0) is None


def test_nome_e_engajamento_qualitativo_por_regra():
    base = _base_exemplo()
    globais = cc.medianas_globais(base)
    m1 = cc.metricas_cluster(base, 1)
    nome = cc.nome_cluster(1, m1, globais)
    assert nome.startswith("Duração muito acima da mediana")
    assert "engajamento muito acima da mediana" in nome
    assert cc.engajamento_qualitativo(m1, globais) == "alto"
    m0 = cc.metricas_cluster(base, 0)
    assert cc.nome_cluster(0, m0, globais) == "Perfil típico (próximo da mediana)"
    assert cc.engajamento_qualitativo(m0, globais) == "médio"


def test_nome_sem_dado():
    vazio = {"duracao_mediana": None, "engajamento_mediano": None}
    assert cc.nome_cluster(0, vazio, {"duracao": None, "engajamento": None}) == "Sem dados suficientes"


def test_cluster_pequeno_tem_aviso_e_recomendacao_sem_generalizar():
    base = _base_exemplo()
    globais = cc.medianas_globais(base)
    m1 = cc.metricas_cluster(base, 1)
    assert "não generalize" in cc.aviso_poucos_reels(m1["n_reels"])
    assert cc.aviso_poucos_reels(6) is None
    assert "Amostra pequena" in cc.recomendacao_cluster(m1, globais, None, None)


def test_recomendacao_associativa_nunca_causal():
    base = _base_exemplo()
    globais = cc.medianas_globais(base)
    m0 = cc.metricas_cluster(base, 0)
    texto = cc.recomendacao_cluster(m0, globais, None, None)
    assert "próximo da mediana" in texto
    forte = dict(m0, engajamento_mediano=100.0)
    texto = cc.recomendacao_cluster(forte, globais, None, None)
    assert "associados" in texto
    assert "causa" not in texto.lower()


def test_descricao_do_cluster():
    base = _base_exemplo()
    globais = cc.medianas_globais(base)
    m1 = cc.metricas_cluster(base, 1)
    d = cc.descricao_cluster(1, m1, globais, len(base), "Nome X")
    assert d["titulo"] == "Nome X"
    assert "2 reels (25%" in d["subtitulo"]
    assert "muito acima da mediana" in d["texto"]


# --- sentimento --------------------------------------------------------------


def _comentarios(linhas: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(linhas, columns=["id_reel", "sentiment_label"])


def test_composicao_junta_por_id_reel_e_ignora_outros_clusters():
    base = _base_exemplo()
    com = _comentarios(
        [
            ("r1", "positive"),
            ("r2", "negative"),
            ("r3", "neutral"),
            ("r7", "negative"),  # reel de outro cluster
            ("zzz", "positive"),  # reel fora da clusterizacao
        ]
    )
    comp0 = cc.composicao_sentimento(com, base, 0)
    assert comp0["total"] == 3
    assert comp0["contagem"] == {"positive": 1, "neutral": 1, "negative": 1}
    assert round(comp0["pct"]["positive"], 1) == 33.3
    assert cc.composicao_sentimento(com, base, 1)["total"] == 1
    assert cc.composicao_sentimento(com, base, None)["total"] == 4


def test_composicao_cluster_sem_comentarios_e_none():
    base = _base_exemplo()
    com = _comentarios([("r1", "positive")])
    assert cc.composicao_sentimento(com, base, 1) is None


def test_sentimento_vs_global():
    glob = {"pct": {"negative": 20.0}}
    assert cc.sentimento_vs_global({"pct": {"negative": 30.0}}, glob) == 1
    assert cc.sentimento_vs_global({"pct": {"negative": 10.0}}, glob) == -1
    assert cc.sentimento_vs_global({"pct": {"negative": 22.0}}, glob) == 0
    assert cc.sentimento_vs_global(None, glob) is None


# --- governador --------------------------------------------------------------


def test_contagem_e_frase_do_governador():
    base = _base_exemplo()
    ordem = cc.ordenar_clusters(base)
    cont = cc.contagem_governador(base, GOV_A.upper().rstrip("/") + "?x=1")
    assert cont == {"total": 4, "por_cluster": {0: 3, 1: 1}}
    frase = cc.frase_governador(cont, ordem)
    assert frase == "Dos seus 4 reels, 3 estão em Cluster 1 e 1 em Cluster 2."


def test_governador_sem_reels_mensagem_amigavel():
    base = _base_exemplo()
    cont = cc.contagem_governador(base, "https://www.instagram.com/outro/")
    assert cont["total"] == 0
    assert "não tem reels" in cc.frase_governador(cont, [0, 1])
    assert cc.contagem_governador(pd.DataFrame(), GOV_A)["total"] == 0


# --- visual ------------------------------------------------------------------


def test_cores_por_posicao_e_cinza_alem_dos_slots():
    ordem = [0, 1, 2, 3, 4, 5]
    assert cc.cor_cluster(0, ordem, "light") != cc.cor_cluster(0, ordem, "dark")
    assert cc.cor_cluster(5, ordem, "light") == "#8a8a85"


def test_figura_rosca_legenda_com_valores():
    comp = cc.composicao_sentimento(_comentarios([("r1", "positive"), ("r1", "negative")]), _base_exemplo(), 0)
    fig = cc.figura_rosca(comp)
    assert any("50%" in rotulo for rotulo in fig.data[0].labels)


# --- regressao: perfil e frase de decisao inalterados -----------------------


def test_regressao_agrupamento_de_perfil_e_frase_de_decisao():
    assert comparar._nome_grupo(-1) == "Casos atípicos / virais"
    barras = comparar._montar_barras_comparativas(
        {"alcance_proxy": 0.5, "pct_positivo": 0.5, "frequencia": 2.0},
        {
            "alcance_proxy": pd.Series([0.25]),
            "pct_positivo": pd.Series([0.5]),
            "frequencia": pd.Series([2.0]),
        },
    )
    assert "acima da média dos pares" in comparar._frase_decisao("G", barras)
