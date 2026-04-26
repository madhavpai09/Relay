from __future__ import annotations

import hashlib
import hmac
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status

from .config import BASE_DIR, GITHUB_WEBHOOK_SECRET
from .event_decider import should_create_job
from .github_context import build_github_job_context
from .jobs import (
    add_job_log,
    can_run_job,
    create_job,
    get_job_by_delivery_id,
    get_job_by_id,
    get_job_logs,
    list_jobs,
    update_job_status,
)
from .repositories import (
    create_or_update_repository,
    delete_repository,
    get_repository_by_full_name,
    get_repository_by_id,
    list_repositories,
    validate_repository,
)
from .scheduler import scheduler
from .schemas import JobLogCreate, JobStatusUpdate, RepositoryCreate


def _verify_signature(raw_body: bytes, signature_header: str | None) -> dict:
    if not GITHUB_WEBHOOK_SECRET:
        return {"ok": False, "reason": "Missing webhook secret on server"}
    if not signature_header:
        return {"ok": False, "reason": "Missing x-hub-signature-256 header"}

    expected_signature = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode("utf8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if len(signature_header) != len(expected_signature):
        return {"ok": False, "reason": "Signature length mismatch"}

    if not hmac.compare_digest(signature_header, expected_signature):
        return {"ok": False, "reason": "Invalid signature"}

    return {"ok": True}


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler.start()
    try:
        yield
    finally:
        scheduler.stop()


app = FastAPI(title="Relay Master", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "relay-master"}


@app.get("/repositories")
def repositories_list() -> dict:
    return {"repositories": list_repositories()}


@app.get("/repositories/{repo_id}")
def repositories_get(repo_id: str):
    repository = get_repository_by_id(repo_id)
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repository


@app.post("/repositories", status_code=201)
def repositories_create(body: RepositoryCreate) -> dict:
    result = create_or_update_repository(**body.model_dump())
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["reason"])
    return {"message": "Repository saved", "repository": result["repository"]}


@app.post("/repositories/{repo_id}/validate")
def repositories_validate(repo_id: str) -> dict:
    result = validate_repository(repo_id)
    if not result["ok"]:
        raise HTTPException(status_code=404 if result["reason"] == "Repository not found" else 400, detail=result["reason"])
    return {
        "message": "Repository configuration is valid",
        "repository": result["repository"],
        "pipelinePath": result["pipelinePath"],
        "pipeline": result["pipeline"],
    }


@app.delete("/repositories/{repo_id}")
def repositories_delete(repo_id: str) -> dict:
    result = delete_repository(repo_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result["reason"])
    return {"message": "Repository deleted", "repository": result["repository"]}


@app.get("/jobs")
def jobs_list() -> dict:
    return {"jobs": list_jobs()}


@app.get("/queue")
def queue_snapshot() -> dict:
    return scheduler.get_queue_snapshot()


@app.get("/jobs/{job_id}")
def jobs_get(job_id: str):
    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/jobs/{job_id}/logs")
def jobs_logs(job_id: str) -> dict:
    result = get_job_logs(job_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result["reason"])
    return {"logs": result["logs"]}


@app.patch("/jobs/{job_id}/status")
def jobs_update_status(job_id: str, body: JobStatusUpdate) -> dict:
    result = update_job_status(job_id, body.status)
    if not result["ok"]:
        raise HTTPException(status_code=404 if result["reason"] == "Job not found" else 400, detail=result["reason"])
    return {"message": "Job status updated", "job": result["job"]}


@app.post("/jobs/{job_id}/schedule", status_code=202)
def jobs_schedule(job_id: str) -> dict:
    result = scheduler.schedule_job(job_id)
    if not result["ok"]:
        raise HTTPException(status_code=404 if result["reason"] == "Job not found" else 400, detail=result["reason"])
    return {"message": "Job scheduled", "job": result["job"]}


@app.post("/jobs/{job_id}/run")
def jobs_run(job_id: str) -> dict:
    from .executor import run_job

    result = can_run_job(job_id)
    if not result["ok"]:
        raise HTTPException(status_code=404 if result["reason"] == "Job not found" else 400, detail=result["reason"])

    execution_result = run_job(job_id)
    if not execution_result["ok"]:
        raise HTTPException(
            status_code=404 if execution_result["reason"] == "Job not found" else 400,
            detail=execution_result["reason"],
        )

    return {"message": "Job run completed", "job": execution_result["job"]}


@app.post("/jobs/{job_id}/logs", status_code=201)
def jobs_add_log(job_id: str, body: JobLogCreate) -> dict:
    result = add_job_log(job_id, level=body.level, message=body.message)
    if not result["ok"]:
        raise HTTPException(status_code=404 if result["reason"] == "Job not found" else 400, detail=result["reason"])
    return {"message": "Job log added", "log": result["entry"]}


@app.post("/webhooks/github", status_code=202)
async def github_webhook(request: Request):
    raw_body = await request.body()
    signature_header = request.headers.get("x-hub-signature-256")
    event = request.headers.get("x-github-event")
    delivery_id = request.headers.get("x-github-delivery")

    verification = _verify_signature(raw_body, signature_header)
    if not verification["ok"]:
        raise HTTPException(status_code=401, detail=verification["reason"])

    try:
        payload = await request.json()
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from error

    decision = should_create_job(event, payload)
    if not decision["should_create"]:
        repository = payload.get("repository", {}).get("full_name")
        return {
            "status": "ignored",
            "event": event,
            "deliveryId": delivery_id,
            "repository": repository,
            "reason": decision["reason"],
        }

    github_context = build_github_job_context(event, payload)
    registered_repository = get_repository_by_full_name(github_context["repository"])
    workspace_path = registered_repository["localPath"] if registered_repository else str(BASE_DIR)
    pipeline_file = registered_repository["pipelineFile"] if registered_repository else ".relay.yml"

    existing_job = get_job_by_delivery_id(delivery_id)
    if existing_job:
        return {
            "status": "duplicate",
            "event": event,
            "deliveryId": delivery_id,
            "repository": github_context["repository"],
            "jobId": existing_job["id"],
            "jobStatus": existing_job["status"],
            "workspacePath": existing_job["workspacePath"] or workspace_path,
            "reason": "This webhook delivery was already processed",
        }

    job = create_job(
        event=event or "unknown",
        delivery_id=delivery_id or str(Path.cwd()),
        repository=github_context["repository"],
        trigger_type=github_context["trigger_type"],
        ref=github_context["ref"],
        commit_sha=github_context["commit_sha"],
        pull_request_number=github_context["pull_request_number"],
        action=github_context["action"],
        base_ref=github_context["base_ref"],
        head_ref=github_context["head_ref"],
        workspace_path=workspace_path,
        pipeline_file=pipeline_file,
        payload=payload,
    )

    scheduler.schedule_job(job["id"])

    return {
        "status": "accepted",
        "event": event,
        "deliveryId": delivery_id,
        "repository": job["repository"],
        "jobId": job["id"],
        "jobStatus": job["status"],
        "triggerType": job["triggerType"],
        "ref": job["ref"],
        "commitSha": job["commitSha"],
        "pullRequestNumber": job["pullRequestNumber"],
        "workspacePath": job["workspacePath"],
        "queueStatus": "scheduled",
    }
