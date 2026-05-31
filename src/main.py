from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.infra.db import create_pool
from src.infra.observability import configure_logging
from src.infra.qdrant import create_qdrant


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    app.state.db_pool = await create_pool()
    app.state.qdrant = create_qdrant()
    yield
    await app.state.db_pool.close()


app = FastAPI(title="SMART_bot", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    db_ok = False
    qdrant_ok = False
    try:
        async with app.state.db_pool.acquire() as c:
            await c.fetchval("SELECT 1")
            db_ok = True
    except Exception:
        pass
    try:
        await app.state.qdrant.get_collections()
        qdrant_ok = True
    except Exception:
        pass
    return {
        "status": "ok",
        "db": "ok" if db_ok else "fail",
        "qdrant": "ok" if qdrant_ok else "fail",
    }
