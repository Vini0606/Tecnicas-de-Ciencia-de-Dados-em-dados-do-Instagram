from unittest.mock import MagicMock

import pandas as pd


def _fake_repo():
    fake_repo = MagicMock()
    fake_repo.load_reels.return_value = pd.DataFrame({"id": ["r1"]})
    fake_repo.load_comments.return_value = pd.DataFrame({"text": ["oi"]})
    fake_repo.load_posts.return_value = pd.DataFrame({"id": ["p1"]})
    fake_repo.load_profiles.return_value = pd.DataFrame({"id": ["gov1"]})
    return fake_repo


def test_run_le_silver_e_chama_run_deterministic_modeling(monkeypatch):
    import scripts.run_modeling as run_modeling_script

    fake_repo = _fake_repo()
    monkeypatch.setattr("scripts.run_modeling.DeltaRepository", lambda **kwargs: fake_repo)

    fake_result = MagicMock(run_id="run_abc")
    fake_run_deterministic_modeling = MagicMock(return_value=fake_result)
    monkeypatch.setattr(
        "scripts.run_modeling.run_deterministic_modeling", fake_run_deterministic_modeling
    )

    run_id = run_modeling_script.run(run_id="run_fixo")

    assert run_id == "run_abc"
    fake_run_deterministic_modeling.assert_called_once()
    args, kwargs = fake_run_deterministic_modeling.call_args
    assert args[0] is fake_repo.load_reels.return_value
    assert args[1] is fake_repo.load_comments.return_value
    # ADR 0019 (parte C): o novo passo [PERFORMANCE-POR-POST] precisa de
    # posts_clean e do governor_engagement (Gold) já carregados aqui.
    assert args[2] is fake_repo.load_posts.return_value
    assert args[3] is fake_repo.load_profiles.return_value
    assert kwargs["run_id"] == "run_fixo"


def test_run_repassa_parent_run_id_para_o_orquestrador(monkeypatch):
    import scripts.run_modeling as run_modeling_script

    fake_repo = _fake_repo()
    monkeypatch.setattr("scripts.run_modeling.DeltaRepository", lambda **kwargs: fake_repo)

    fake_run_deterministic_modeling = MagicMock(return_value=MagicMock(run_id="run_abc"))
    monkeypatch.setattr(
        "scripts.run_modeling.run_deterministic_modeling", fake_run_deterministic_modeling
    )

    run_modeling_script.run(run_id="run_fixo", parent_run_id="run_extracao_pai")

    kwargs = fake_run_deterministic_modeling.call_args.kwargs
    assert kwargs["parent_run_id"] == "run_extracao_pai"


def test_run_sem_run_id_deixa_orquestrador_gerar_um_novo(monkeypatch):
    import scripts.run_modeling as run_modeling_script

    fake_repo = _fake_repo()
    monkeypatch.setattr("scripts.run_modeling.DeltaRepository", lambda **kwargs: fake_repo)

    fake_run_deterministic_modeling = MagicMock(return_value=MagicMock(run_id="gerado"))
    monkeypatch.setattr(
        "scripts.run_modeling.run_deterministic_modeling", fake_run_deterministic_modeling
    )

    run_modeling_script.run()

    kwargs = fake_run_deterministic_modeling.call_args.kwargs
    assert kwargs["run_id"] is None
