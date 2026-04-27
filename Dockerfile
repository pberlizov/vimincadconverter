FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MESH2CAD_STATE_DIR=/data/state \
    MESH2CAD_BIND_HOST=0.0.0.0 \
    MESH2CAD_BIND_PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip setuptools wheel \
    && pip install -e ".[api]"

RUN useradd --create-home --uid 1000 mesh2cad \
    && mkdir -p /data/state \
    && chown -R mesh2cad:mesh2cad /app /data

USER mesh2cad

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:$MESH2CAD_BIND_PORT/ready" >/dev/null || exit 1

CMD ["mesh2cad-api"]
