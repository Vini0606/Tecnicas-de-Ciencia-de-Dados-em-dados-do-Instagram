import json
from unittest.mock import MagicMock


def _payload_stream(data: dict | str):
    body = data if isinstance(data, str) else json.dumps(data)
    return MagicMock(read=MagicMock(return_value=body.encode("utf-8")))


def _set_function_names(monkeypatch):
    monkeypatch.setenv("EXTRACT_FUNCTION_NAME", "extract-fn")
    monkeypatch.setenv("TRANSFORM_FUNCTION_NAME", "transform-fn")
    monkeypatch.setenv("LOAD_FUNCTION_NAME", "load-fn")


def test_orchestrator_encadeia_as_3_lambdas_e_propaga_run_id(monkeypatch):
    from lambdas.orchestrator import handler as orchestrator_handler

    _set_function_names(monkeypatch)

    responses = {
        "extract-fn": {
            "statusCode": 200,
            "body": json.dumps({"run_id": "generated-run", "profiles": 1, "posts": 1, "reels": 1}),
        },
        "transform-fn": {
            "statusCode": 200,
            "body": json.dumps({"run_id": "generated-run", "status": "silver_complete"}),
        },
        "load-fn": {
            "statusCode": 200,
            "body": json.dumps({"run_id": "generated-run", "status": "gold_complete"}),
        },
    }
    invoked = []

    def fake_invoke(FunctionName, InvocationType, Payload):
        invoked.append((FunctionName, json.loads(Payload)))
        return {"Payload": _payload_stream(responses[FunctionName])}

    fake_client = MagicMock()
    fake_client.invoke.side_effect = fake_invoke
    monkeypatch.setattr("boto3.client", lambda service: fake_client)

    resp = orchestrator_handler.handler({"links": ["https://www.instagram.com/exemplo/"]}, {})

    assert resp["statusCode"] == 200
    assert json.loads(resp["body"]) == {"run_id": "generated-run", "status": "pipeline_complete"}

    assert [name for name, _ in invoked] == ["extract-fn", "transform-fn", "load-fn"]
    # extract recebe os links e o run_id de entrada (None); transform/load recebem
    # o run_id que veio da resposta de extract, não o de entrada.
    assert invoked[0][1] == {"links": ["https://www.instagram.com/exemplo/"], "run_id": None}
    assert invoked[1][1] == {"run_id": "generated-run"}
    assert invoked[2][1] == {"run_id": "generated-run"}


def test_orchestrator_aborta_e_nao_chama_as_proximas_etapas_se_uma_falhar(monkeypatch):
    from lambdas.orchestrator import handler as orchestrator_handler

    _set_function_names(monkeypatch)

    responses = {
        "extract-fn": {"statusCode": 200, "body": json.dumps({"run_id": "generated-run"})},
        "transform-fn": {"statusCode": 400, "body": "Missing run_id in event"},
    }
    invoked = []

    def fake_invoke(FunctionName, InvocationType, Payload):
        invoked.append(FunctionName)
        return {"Payload": _payload_stream(responses[FunctionName])}

    fake_client = MagicMock()
    fake_client.invoke.side_effect = fake_invoke
    monkeypatch.setattr("boto3.client", lambda service: fake_client)

    resp = orchestrator_handler.handler({"links": []}, {})

    assert resp["statusCode"] == 500
    body = json.loads(resp["body"])
    assert body["stage"] == "transform"

    assert invoked == ["extract-fn", "transform-fn"]
