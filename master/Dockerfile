FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash master

WORKDIR /app

COPY master/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY master/ /app/master/

RUN mkdir -p /app/data && chown master:master /app/data

USER master
EXPOSE 9210

CMD ["python", "-m", "master.app"]
