from __future__ import annotations

from contextlib import asynccontextmanager

from .routers import jobs, repositories, simulation, ui, workers
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routers import webhooks
from .config import BASE_DIR
from .services.scheduler import scheduler
from .services.simulation import traffic_simulator


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler.start()
    try:
        yield
    finally:
        traffic_simulator.stop()
        scheduler.stop()


app = FastAPI(title="Relay", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(ui.router)
app.include_router(repositories.router)
app.include_router(jobs.router)
app.include_router(webhooks.router)
app.include_router(workers.router)
app.include_router(simulation.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "relay"}


@app.get("/queue")
def queue_snapshot() -> dict:
    return scheduler.get_queue_snapshot()
