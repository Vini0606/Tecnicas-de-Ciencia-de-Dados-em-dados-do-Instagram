# Contexto de build: raiz do repositorio (nao este diretorio) -- o handler
# importa de src/. Sem apify-client nem modelagem pesada (ADR 0039).
# docker build -f lambdas/rebuild/Dockerfile -t rebuild .
FROM public.ecr.aws/lambda/python:3.12

COPY lambdas/rebuild/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY src/__init__.py src/delta_io.py src/schemas_delta.py src/run_id.py ${LAMBDA_TASK_ROOT}/src/
COPY src/coleta/ ${LAMBDA_TASK_ROOT}/src/coleta/
COPY src/features/ ${LAMBDA_TASK_ROOT}/src/features/
COPY src/data_extract/bronze_writer.py ${LAMBDA_TASK_ROOT}/src/data_extract/
COPY lambdas/rebuild/handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
