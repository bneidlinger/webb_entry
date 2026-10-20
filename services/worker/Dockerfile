FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY services/api /app/api
COPY services/worker /app/worker-service
RUN pip install --upgrade pip && pip install /app/api /app/worker-service
WORKDIR /app/worker-service

CMD ["python", "-m", "worker.run"]
