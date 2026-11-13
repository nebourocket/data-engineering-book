FROM python:3.12-slim
# git と bash は 3 章（Linux・シェル・Git）のコード例を動かすために入れます。
RUN apt-get update \
    && apt-get install -y --no-install-recommends git bash \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /w
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
