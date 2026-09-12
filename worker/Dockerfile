FROM python:3.11-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TF_CPP_MIN_LOG_LEVEL=2 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    MODEL_MANIFEST=/app/config/models.json \
    MODEL_DIR=/models \
    PYTHONPATH=/app/worker/src

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY worker/pyproject.toml /app/worker/pyproject.toml
COPY worker/requirements.lock /app/worker/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /app/worker/requirements.lock
COPY worker/src /app/worker/src
COPY config /app/config

RUN useradd --create-home --uid 10001 worker \
    && chmod -R a+rX /app/worker /app/config \
    && install -d -o worker -g worker /models
USER worker

CMD ["python", "-m", "ihear_worker.main"]

FROM runtime AS test
USER root
COPY worker/tests /app/worker/tests
COPY worker/requirements-test.lock /app/worker/requirements-test.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /app/worker/requirements-test.lock
RUN chown -R worker:worker /app/worker
USER worker
WORKDIR /app/worker
CMD ["pytest"]

FROM runtime AS production
