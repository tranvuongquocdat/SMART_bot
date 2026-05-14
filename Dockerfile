FROM python:3.12-slim

# Node 22 for the Zalo bridge (zca-js).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && apt-get purge -y curl gnupg \
 && rm -rf /var/lib/apt/lists/*

# uv (fast Python package manager).
COPY --from=ghcr.io/astral-sh/uv:0.9.22 /uv /uvx /usr/local/bin/

WORKDIR /app

# Python deps (cached layer).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Node deps for the Zalo bridge (cached layer; isolated to its own dir).
COPY src/channels/zalo_bridge/package.json src/channels/zalo_bridge/package.json
RUN cd src/channels/zalo_bridge && npm install --omit=dev --no-audit --no-fund

# App source. node_modules from the previous step is preserved (COPY merges).
COPY src/ src/

# Inbound file scratch dir (mounted as part of data/ volume in compose,
# but must exist on first run before any download).
RUN mkdir -p data/inbound

ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "24702"]
