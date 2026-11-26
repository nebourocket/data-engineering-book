FROM python:3.12.8-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 依存だけ先にコピーして入れる。コードを直しても、この層はキャッシュが効く。
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 普通のユーザーで動かす (root のままにしない)。
RUN useradd --create-home --uid 10001 etl
COPY --chown=etl:etl storage.py etl.py ./
USER etl

CMD ["python", "etl.py"]
