ARG PYTHON_IMAGE=python:3.12-slim
ARG APT_MIRROR=deb.debian.org
ARG PIP_INDEX_URL=https://pypi.org/simple

FROM ${PYTHON_IMAGE}

# Re-declare ARGs after FROM so they are available in RUN instructions
ARG APT_MIRROR
ARG PIP_INDEX_URL

# Switch apt source to mirror if APT_MIRROR is set
RUN sed -i "s|http://deb.debian.org|http://${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources

RUN apt-get update && apt-get install -y --no-install-recommends curl procps \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash worker

WORKDIR /app

COPY worker/requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt

COPY shared/ /app/shared/
COPY worker/ /app/worker/

RUN mkdir -p /workspace && chown worker:worker /workspace

USER worker

CMD ["python", "-m", "worker.daemon"]
