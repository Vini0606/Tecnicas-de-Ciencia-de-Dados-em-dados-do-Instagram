# Contexto de build: raiz do repositório (não este diretório) -- o handler
# importa de src/, ex.: src.features.silver.*.
# docker build -f lambdas/transform/Dockerfile -t transform .
FROM public.ecr.aws/lambda/python:3.12

COPY lambdas/transform/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY src/ ${LAMBDA_TASK_ROOT}/src/
COPY lambdas/transform/handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
