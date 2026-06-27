FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl procps \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash worker

WORKDIR /app

COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY worker/ /app/worker/

RUN mkdir -p /workspace && chown worker:worker /workspace

USER worker

CMD ["python", "-m", "worker.daemon"]
