# Contexto de build: raiz do repositório (não este diretório) -- o handler
# importa de src/, ex.: src.modeling.profile_clustering.
# docker build -f lambdas/model/Dockerfile -t model .
#
# Sem torch/transformers/bertopic de propósito: o clustering de PERFIL por
# Engajamento (Fase 2) só consome métricas já agregadas em governor_engagement
# -- scikit-learn/hyperopt bastam (AutoClusterHPO), nada de inferência de NLP
# nesta Lambda.
FROM public.ecr.aws/lambda/python:3.12

COPY lambdas/model/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY src/ ${LAMBDA_TASK_ROOT}/src/
COPY lambdas/model/handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
