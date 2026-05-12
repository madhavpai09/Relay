from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from ..config import BASE_DIR, GITHUB_WEBHOOK_SECRET
from ..services.event_decider import should_create_job
from ..services.github_context import build_github_job_context
from ..services.language import infer_repository_language
from ..services.jobs import create_job, get_job_by_delivery_id
from ..services.priority import compute_job_priority
from ..services.repositories import get_repository_by_full_name
from ..services.scheduler import scheduler

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


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


@router.post("/github", status_code=202)
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
    language = (
        registered_repository["language"]
        if registered_repository
        else infer_repository_language(workspace_path)
    )

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

    priority = compute_job_priority(
        trigger_type=github_context["trigger_type"],
        ref=github_context["ref"],
        payload=payload,
        repository=registered_repository,
    )

    job = create_job(
        event=event or "unknown",
        delivery_id=delivery_id or str(Path.cwd()),
        repository=github_context["repository"],
        trigger_type=github_context["trigger_type"],
        language=language,
        ref=github_context["ref"],
        commit_sha=github_context["commit_sha"],
        pull_request_number=github_context["pull_request_number"],
        action=github_context["action"],
        base_ref=github_context["base_ref"],
        head_ref=github_context["head_ref"],
        workspace_path=workspace_path,
        pipeline_file=pipeline_file,
        priority_label=priority["label"],
        priority_score=priority["score"],
        priority_reason=priority["reason"],
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
        "language": job["language"],
        "priorityLabel": job["priorityLabel"],
        "priorityScore": job["priorityScore"],
        "ref": job["ref"],
        "commitSha": job["commitSha"],
        "pullRequestNumber": job["pullRequestNumber"],
        "workspacePath": job["workspacePath"],
        "queueStatus": "scheduled",
    }
