import json
import os

import boto3

STAGE_EXTRACT = "extract"
STAGE_TRANSFORM = "transform"
STAGE_LOAD = "load"


def _invoke(client, function_name: str, payload: dict) -> dict:
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    return json.loads(response["Payload"].read())


def _stage_error(stage: str, result: dict) -> dict:
    # Uma falha tratada (statusCode != 200) traz a mensagem em "body"; uma
    # exceção não tratada dentro da sub-Lambda não passa por esse contrato e
    # vem, em vez disso, como {"errorMessage", "errorType", "stackTrace"}.
    error = result["errorMessage"] if "errorMessage" in result else result.get("body")
    return {
        "statusCode": 500,
        "body": json.dumps({"stage": stage, "error": error}),
    }


def handler(event, context):
    links = event.get("links", [])
    run_id = event.get("run_id")

    client = boto3.client("lambda")

    extract_result = _invoke(
        client, os.environ["EXTRACT_FUNCTION_NAME"], {"links": links, "run_id": run_id}
    )
    if extract_result.get("statusCode") != 200:
        return _stage_error(STAGE_EXTRACT, extract_result)
    run_id = json.loads(extract_result["body"])["run_id"]

    transform_result = _invoke(
        client, os.environ["TRANSFORM_FUNCTION_NAME"], {"run_id": run_id}
    )
    if transform_result.get("statusCode") != 200:
        return _stage_error(STAGE_TRANSFORM, transform_result)

    load_result = _invoke(client, os.environ["LOAD_FUNCTION_NAME"], {"run_id": run_id})
    if load_result.get("statusCode") != 200:
        return _stage_error(STAGE_LOAD, load_result)

    return {
        "statusCode": 200,
        "body": json.dumps({"run_id": run_id, "status": "pipeline_complete"}),
    }
