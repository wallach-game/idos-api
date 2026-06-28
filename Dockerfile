FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir fastapi==0.115.0 uvicorn[standard]==0.30.0 playwright==1.44.0 httpx==0.27.0

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
RUN playwright install && playwright install-deps

RUN useradd -m appuser
RUN chown -R appuser:appuser /opt/ms-playwright
USER appuser
WORKDIR /app
COPY ./app.py ./routes.py ./peers.py ./proxies.py ./

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
