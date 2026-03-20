FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system packages and a modern Rust toolchain to build Tectonic.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    pkg-config \
    libssl-dev \
    libfreetype6-dev \
    libgraphite2-dev \
    libharfbuzz-dev \
    && curl https://sh.rustup.rs -sSf | sh -s -- -y --profile minimal --default-toolchain stable \
    && /root/.cargo/bin/rustc --version \
    && /root/.cargo/bin/cargo install tectonic \
    && cp /root/.cargo/bin/tectonic /usr/local/bin/tectonic \
    && which tectonic \
    && tectonic --version \
    && rm -rf /var/lib/apt/lists/* /root/.cargo/registry /root/.cargo/git

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.main:fastapi_app --host 0.0.0.0 --port ${PORT:-8000}"]