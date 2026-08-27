# Contexto de build: raiz do repositório (não este diretório) -- o handler
# importa de src/, ex.: src.features.gold.engagement_aggregator.
# docker build -f lambdas/load/Dockerfile -t load .
FROM public.ecr.aws/lambda/python:3.12

COPY lambdas/load/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY src/ ${LAMBDA_TASK_ROOT}/src/
COPY lambdas/load/handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
