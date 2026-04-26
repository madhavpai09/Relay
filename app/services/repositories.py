from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import uuid

from ..config import DEFAULT_PIPELINE_FILE
from ..database import db_lock, fetch_all, fetch_one, transaction
from .pipeline import load_pipeline_definition


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _map_repository(row) -> dict | None:
    if row is None:
        return None

    return {
        "id": row["id"],
        "fullName": row["full_name"],
        "provider": row["provider"],
        "localPath": row["local_path"],
        "defaultBranch": row["default_branch"],
        "pipelineFile": row["pipeline_file"],
        "active": bool(row["active"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _validate_local_repository_path(local_path: str) -> dict:
    if not local_path:
        return {"ok": False, "reason": "localPath is required"}

    absolute_path = Path(local_path).expanduser().resolve()

    if not absolute_path.exists():
        return {"ok": False, "reason": f"Repository path does not exist: {absolute_path}"}

    if not absolute_path.is_dir():
        return {"ok": False, "reason": f"Repository path is not a directory: {absolute_path}"}

    return {"ok": True, "absolute_path": str(absolute_path)}


_REPO_COLUMNS = "id, full_name, provider, local_path, default_branch, pipeline_file, active, created_at, updated_at"


def list_repositories() -> list[dict]:
    return [
        _map_repository(row)
        for row in fetch_all(f"SELECT {_REPO_COLUMNS} FROM repositories ORDER BY full_name ASC")
    ]


def get_repository_by_id(repo_id: str) -> dict | None:
    return _map_repository(
        fetch_one(f"SELECT {_REPO_COLUMNS} FROM repositories WHERE id = ?", (repo_id,))
    )


def get_repository_by_full_name(full_name: str | None) -> dict | None:
    if not full_name:
        return None
    return _map_repository(
        fetch_one(f"SELECT {_REPO_COLUMNS} FROM repositories WHERE full_name = ?", (full_name,))
    )


def create_or_update_repository(
    *,
    fullName: str,
    provider: str = "github",
    localPath: str,
    defaultBranch: str = "main",
    pipelineFile: str = DEFAULT_PIPELINE_FILE,
    active: bool = True,
) -> dict:
    if not fullName:
        return {"ok": False, "reason": "fullName is required"}

    path_validation = _validate_local_repository_path(localPath)
    if not path_validation["ok"]:
        return path_validation

    existing = get_repository_by_full_name(fullName)
    now = _now()
    repo_id = existing["id"] if existing else str(uuid.uuid4())
    created_at = existing["createdAt"] if existing else now

    with db_lock:
        conn = transaction()
        conn.execute(
            """
            INSERT INTO repositories (
                id, full_name, provider, local_path, default_branch, pipeline_file, active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(full_name) DO UPDATE SET
                provider = excluded.provider,
                local_path = excluded.local_path,
                default_branch = excluded.default_branch,
                pipeline_file = excluded.pipeline_file,
                active = excluded.active,
                updated_at = excluded.updated_at
            """,
            (
                repo_id, fullName, provider,
                path_validation["absolute_path"],
                defaultBranch, pipelineFile,
                1 if active else 0,
                created_at, now,
            ),
        )
        conn.commit()

    return {"ok": True, "repository": get_repository_by_full_name(fullName)}


def validate_repository(repo_id: str) -> dict:
    repository = get_repository_by_id(repo_id)
    if not repository:
        return {"ok": False, "reason": "Repository not found"}

    path_validation = _validate_local_repository_path(repository["localPath"])
    if not path_validation["ok"]:
        return path_validation

    pipeline_result = load_pipeline_definition(repository["localPath"], repository["pipelineFile"])
    if not pipeline_result["ok"]:
        return {"ok": False, "reason": pipeline_result["reason"]}

    return {
        "ok": True,
        "repository": repository,
        "pipeline": pipeline_result["pipeline"],
        "pipelinePath": pipeline_result["pipeline_path"],
    }


def delete_repository(repo_id: str) -> dict:
    repository = get_repository_by_id(repo_id)
    if not repository:
        return {"ok": False, "reason": "Repository not found"}

    with db_lock:
        conn = transaction()
        conn.execute("DELETE FROM repositories WHERE id = ?", (repo_id,))
        conn.commit()

    return {"ok": True, "repository": repository}
