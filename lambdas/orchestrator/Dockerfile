# Contexto de build: raiz do repositório (não este diretório) --
# ex.: docker build -f lambdas/orchestrator/Dockerfile -t orchestrator .
FROM public.ecr.aws/lambda/python:3.12

COPY lambdas/orchestrator/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY lambdas/orchestrator/handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
