FROM python:3.11-slim-bookworm

WORKDIR /app

# Pipecat / onnxruntime / soundfile runtime libs
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY server/pyproject.toml server/README.md ./
COPY server/app ./app

RUN pip install --no-cache-dir .

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
