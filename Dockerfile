FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system packages needed to compile and run Tectonic.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    cargo \
    pkg-config \
    libssl-dev \
    libfreetype6-dev \
    libgraphite2-dev \
    libharfbuzz-dev \
    && cargo install tectonic --locked \
    && which tectonic \
    && tectonic --version \
    && apt-get purge -y build-essential pkg-config libssl-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /root/.cargo/registry /root/.cargo/git

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.main:fastapi_app --host 0.0.0.0 --port ${PORT:-8000}"]