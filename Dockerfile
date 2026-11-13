FROM python:3.12-slim
# git と bash は 3 章（Linux・シェル・Git）のコード例を動かすために入れます。
# fonts-noto-cjk は図の日本語ラベルのために入れます（matplotlib は OS のフォントを使います）。
RUN apt-get update \
    && apt-get install -y --no-install-recommends git bash fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /w
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
