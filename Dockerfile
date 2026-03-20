FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system packages needed for running the app and Tectonic.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    tectonic \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.main:fastapi_app --host 0.0.0.0 --port ${PORT:-8000}"]