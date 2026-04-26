from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import uuid

from ..config import DATABASE_PATH, DEFAULT_PIPELINE_FILE
from ..database import db_lock, fetch_all, fetch_one, transaction


# Status lifecycle: received -> in_queue -> processing -> processed -> sent
# Any status can transition to failed.
ALLOWED_STATUSES = {"received", "in_queue", "processing", "processed", "sent", "failed"}

LEGACY_JOBS_FILE = DATABASE_PATH.parent / "jobs.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _map_log(row) -> dict:
    return {
        "id": row["id"],
        "timestamp": row["timestamp"],
        "level": row["level"],
        "message": row["message"],
    }


def _get_logs_for_job(job_id: str) -> list[dict]:
    return [
        _map_log(row)
        for row in fetch_all(
            """
            SELECT id, timestamp, level, message
            FROM job_logs
            WHERE job_id = ?
            ORDER BY timestamp ASC
            """,
            (job_id,),
        )
    ]


def _map_job(row) -> dict | None:
    if row is None:
        return None

    return {
        "id": row["id"],
        "event": row["event"],
        "deliveryId": row["delivery_id"],
        "repository": row["repository"],
        "triggerType": row["trigger_type"],
        "ref": row["ref"],
        "commitSha": row["commit_sha"],
        "pullRequestNumber": row["pull_request_number"],
        "action": row["action"],
        "baseRef": row["base_ref"],
        "headRef": row["head_ref"],
        "workspacePath": row["workspace_path"],
        "pipelineFile": row["pipeline_file"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "startedAt": row["started_at"],
        "completedAt": row["completed_at"],
        "logs": _get_logs_for_job(row["id"]),
        "payload": json.loads(row["payload_json"]),
    }


def _insert_log(job_id: str, *, level: str = "info", message: str, log_id: str | None = None, timestamp: str | None = None) -> dict:
    entry = {
        "id": log_id or str(uuid.uuid4()),
        "timestamp": timestamp or _now(),
        "level": level,
        "message": message,
    }

    conn = transaction()
    conn.execute(
        """
        INSERT INTO job_logs (id, job_id, timestamp, level, message)
        VALUES (?, ?, ?, ?, ?)
        """,
        (entry["id"], job_id, entry["timestamp"], entry["level"], entry["message"]),
    )
    return entry


_JOB_COLUMNS = """
    id, event, delivery_id, repository, trigger_type, ref, commit_sha,
    pull_request_number, action, base_ref, head_ref, workspace_path,
    pipeline_file, status, created_at, started_at, completed_at, payload_json
"""


def list_jobs() -> list[dict]:
    return [
        _map_job(row)
        for row in fetch_all(f"SELECT {_JOB_COLUMNS} FROM jobs ORDER BY created_at DESC")
    ]


def get_job_by_id(job_id: str) -> dict | None:
    return _map_job(
        fetch_one(f"SELECT {_JOB_COLUMNS} FROM jobs WHERE id = ?", (job_id,))
    )


def get_job_by_delivery_id(delivery_id: str) -> dict | None:
    return _map_job(
        fetch_one(f"SELECT {_JOB_COLUMNS} FROM jobs WHERE delivery_id = ?", (delivery_id,))
    )


def create_job(
    *,
    event: str,
    delivery_id: str,
    repository: str | None,
    trigger_type: str,
    ref: str | None,
    commit_sha: str | None,
    pull_request_number: int | None,
    action: str | None,
    base_ref: str | None,
    head_ref: str | None,
    workspace_path: str,
    pipeline_file: str = DEFAULT_PIPELINE_FILE,
    payload: dict,
) -> dict:
    job_id = str(uuid.uuid4())
    created_at = _now()

    with db_lock:
        conn = transaction()
        conn.execute("BEGIN")
        try:
            conn.execute(
                f"""
                INSERT INTO jobs (
                    id, event, delivery_id, repository, trigger_type, ref, commit_sha,
                    pull_request_number, action, base_ref, head_ref, workspace_path,
                    pipeline_file, status, created_at, started_at, completed_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id, event, delivery_id, repository, trigger_type, ref, commit_sha,
                    pull_request_number, action, base_ref, head_ref, workspace_path,
                    pipeline_file, "received", created_at, None, None, json.dumps(payload),
                ),
            )
            _insert_log(job_id, level="info", message=f"Job received for {trigger_type} event", timestamp=created_at)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return get_job_by_id(job_id)


def update_job_status(job_id: str, next_status: str) -> dict:
    job = get_job_by_id(job_id)
    if not job:
        return {"ok": False, "reason": "Job not found"}
    if next_status not in ALLOWED_STATUSES:
        return {"ok": False, "reason": f'Invalid status "{next_status}"'}

    started_at = _now() if next_status == "processing" and not job["startedAt"] else job["startedAt"]
    terminal = {"processed", "sent", "failed"}
    completed_at = _now() if next_status in terminal and not job["completedAt"] else job["completedAt"]

    with db_lock:
        conn = transaction()
        conn.execute("BEGIN")
        try:
            conn.execute(
                "UPDATE jobs SET status = ?, started_at = ?, completed_at = ? WHERE id = ?",
                (next_status, started_at, completed_at, job_id),
            )
            _insert_log(
                job_id,
                level="error" if next_status == "failed" else "info",
                message=f"Job status changed to {next_status}",
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return {"ok": True, "job": get_job_by_id(job_id)}


def can_run_job(job_id: str) -> dict:
    job = get_job_by_id(job_id)
    if not job:
        return {"ok": False, "reason": "Job not found"}
    if job["status"] == "processing":
        return {"ok": False, "reason": "Job is already processing"}
    return {"ok": True, "job": job}


def add_job_log(job_id: str, *, level: str = "info", message: str) -> dict:
    job = get_job_by_id(job_id)
    if not job:
        return {"ok": False, "reason": "Job not found"}
    if not message:
        return {"ok": False, "reason": "Log message is required"}

    with db_lock:
        conn = transaction()
        conn.execute("BEGIN")
        try:
            entry = _insert_log(job_id, level=level, message=message)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return {"ok": True, "entry": entry, "job": get_job_by_id(job_id)}


def get_job_logs(job_id: str) -> dict:
    job = get_job_by_id(job_id)
    if not job:
        return {"ok": False, "reason": "Job not found"}
    return {"ok": True, "logs": _get_logs_for_job(job_id)}


def get_next_queued_job() -> dict | None:
    row = fetch_one(
        f"SELECT {_JOB_COLUMNS} FROM jobs WHERE status = 'in_queue' ORDER BY created_at ASC LIMIT 1"
    )
    return _map_job(row)


def migrate_legacy_json_if_needed() -> None:
    count_row = fetch_one("SELECT COUNT(*) AS count FROM jobs")
    if count_row["count"] > 0 or not LEGACY_JOBS_FILE.exists():
        return

    parsed = json.loads(LEGACY_JOBS_FILE.read_text(encoding="utf8"))
    if not isinstance(parsed, list):
        raise ValueError("Legacy jobs.json must contain a JSON array")

    with db_lock:
        conn = transaction()
        conn.execute("BEGIN")
        try:
            for legacy_job in parsed:
                job_id = legacy_job.get("id") or str(uuid.uuid4())
                conn.execute(
                    f"""
                    INSERT INTO jobs (
                        id, event, delivery_id, repository, trigger_type, ref, commit_sha,
                        pull_request_number, action, base_ref, head_ref, workspace_path,
                        pipeline_file, status, created_at, started_at, completed_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        legacy_job.get("event"),
                        legacy_job.get("deliveryId"),
                        legacy_job.get("repository"),
                        legacy_job.get("triggerType") or legacy_job.get("event"),
                        legacy_job.get("ref"),
                        legacy_job.get("commitSha"),
                        legacy_job.get("pullRequestNumber"),
                        legacy_job.get("action"),
                        legacy_job.get("baseRef"),
                        legacy_job.get("headRef"),
                        legacy_job.get("workspacePath") or str(Path.cwd()),
                        legacy_job.get("pipelineFile") or DEFAULT_PIPELINE_FILE,
                        legacy_job.get("status", "received"),
                        legacy_job.get("createdAt") or _now(),
                        legacy_job.get("startedAt"),
                        legacy_job.get("completedAt"),
                        json.dumps(legacy_job.get("payload", {})),
                    ),
                )

                for legacy_log in legacy_job.get("logs", []):
                    _insert_log(
                        job_id,
                        log_id=legacy_log.get("id"),
                        timestamp=legacy_log.get("timestamp"),
                        level=legacy_log.get("level", "info"),
                        message=legacy_log.get("message", ""),
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


migrate_legacy_json_if_needed()
