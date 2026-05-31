# Production image — local dev uses uvicorn directly per hybrid runtime memory
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv venv && uv pip install -e .

COPY src/ ./src/
COPY migrations/ ./migrations/
COPY config/ ./config/
COPY alembic.ini ./

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
