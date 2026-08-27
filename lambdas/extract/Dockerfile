# Contexto de build: raiz do repositório (não este diretório) -- o handler
# importa de src/, ex.: src.data_extract.bronze_writer.
# docker build -f lambdas/extract/Dockerfile -t extract .
FROM public.ecr.aws/lambda/python:3.12

COPY lambdas/extract/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY src/ ${LAMBDA_TASK_ROOT}/src/
COPY lambdas/extract/handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
