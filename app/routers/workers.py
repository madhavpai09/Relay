from __future__ import annotations

from fastapi import APIRouter

from ..services.workers import worker_pool

router = APIRouter(tags=["workers"])


@router.get("/workers")
def workers_list() -> dict:
    return {"workers": worker_pool.list_workers()}
