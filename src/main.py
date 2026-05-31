from contextlib import asynccontextmanager
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup hooks: DB pool, Qdrant client, EventBus, registries — fill in later tasks
    yield
    # shutdown hooks


app = FastAPI(title="SMART_bot", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
