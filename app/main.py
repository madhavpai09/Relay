from __future__ import annotations

from contextlib import asynccontextmanager

from .routers import jobs, repositories
from fastapi import FastAPI

from .routers import webhooks
from .services.scheduler import scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler.start()
    try:
        yield
    finally:
        scheduler.stop()


app = FastAPI(title="Relay", lifespan=lifespan)

app.include_router(repositories.router)
app.include_router(jobs.router)
app.include_router(webhooks.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "relay"}


@app.get("/queue")
def queue_snapshot() -> dict:
    return scheduler.get_queue_snapshot()
