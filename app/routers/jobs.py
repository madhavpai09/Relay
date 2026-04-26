from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import JobLogCreate, JobStatusUpdate
from ..services.jobs import (
    add_job_log,
    can_run_job,
    get_job_by_id,
    get_job_logs,
    list_jobs,
    update_job_status,
)
from ..services.scheduler import scheduler

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def jobs_list() -> dict:
    return {"jobs": list_jobs()}


@router.get("/{job_id}")
def jobs_get(job_id: str):
    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/logs")
def jobs_logs(job_id: str) -> dict:
    result = get_job_logs(job_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result["reason"])
    return {"logs": result["logs"]}


@router.patch("/{job_id}/status")
def jobs_update_status(job_id: str, body: JobStatusUpdate) -> dict:
    result = update_job_status(job_id, body.status)
    if not result["ok"]:
        raise HTTPException(
            status_code=404 if result["reason"] == "Job not found" else 400,
            detail=result["reason"],
        )
    return {"message": "Job status updated", "job": result["job"]}


@router.post("/{job_id}/schedule", status_code=202)
def jobs_schedule(job_id: str) -> dict:
    result = scheduler.schedule_job(job_id)
    if not result["ok"]:
        raise HTTPException(
            status_code=404 if result["reason"] == "Job not found" else 400,
            detail=result["reason"],
        )
    return {"message": "Job scheduled", "job": result["job"]}


@router.post("/{job_id}/run")
def jobs_run(job_id: str) -> dict:
    from ..services.executor import run_job

    result = can_run_job(job_id)
    if not result["ok"]:
        raise HTTPException(
            status_code=404 if result["reason"] == "Job not found" else 400,
            detail=result["reason"],
        )

    execution_result = run_job(job_id)
    if not execution_result["ok"]:
        raise HTTPException(
            status_code=404 if execution_result["reason"] == "Job not found" else 400,
            detail=execution_result["reason"],
        )

    return {"message": "Job run completed", "job": execution_result["job"]}


@router.post("/{job_id}/logs", status_code=201)
def jobs_add_log(job_id: str, body: JobLogCreate) -> dict:
    result = add_job_log(job_id, level=body.level, message=body.message)
    if not result["ok"]:
        raise HTTPException(
            status_code=404 if result["reason"] == "Job not found" else 400,
            detail=result["reason"],
        )
    return {"message": "Job log added", "log": result["entry"]}
