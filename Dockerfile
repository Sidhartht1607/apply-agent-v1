FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system packages and fetch prebuilt Tectonic binary.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    tar \
    xz-utils \
    && curl -L -o /tmp/tectonic.tar.gz https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-musl.tar.gz \
    && tar -xzf /tmp/tectonic.tar.gz -C /tmp \
    && mv /tmp/tectonic /usr/local/bin/tectonic \
    && chmod +x /usr/local/bin/tectonic \
    && which tectonic \
    && tectonic --version \
    && rm -rf /var/lib/apt/lists/* /tmp/tectonic.tar.gz

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.main:fastapi_app --host 0.0.0.0 --port ${PORT:-8000}"]