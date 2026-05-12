from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import uuid

from ..config import DEFAULT_PIPELINE_FILE
from ..database import db_lock, fetch_all, fetch_one, transaction
from .language import infer_repository_language, normalize_language
from .pipeline import load_pipeline_definition


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _map_repository(row) -> dict | None:
    if row is None:
        return None

    tracked_branches = json.loads(row["tracked_branches_json"]) if row["tracked_branches_json"] else None

    return {
        "id": row["id"],
        "fullName": row["full_name"],
        "provider": row["provider"],
        "localPath": row["local_path"],
        "defaultBranch": row["default_branch"],
        "trackedBranches": tracked_branches or _normalize_tracked_branches(row["default_branch"], None),
        "pipelineFile": row["pipeline_file"],
        "language": row["language"] or "generic",
        "active": bool(row["active"]),
        "verified": bool(row["verified"]),
        "verifiedAt": row["verified_at"],
        "verificationMessage": row["verification_message"],
        "lastPipelinePath": row["last_pipeline_path"],
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


def _update_verification_state(
    repo_id: str,
    *,
    verified: bool,
    verification_message: str,
    verified_at: str | None = None,
    pipeline_path: str | None = None,
    language: str | None = None,
) -> None:
    now = _now()
    with db_lock:
        conn = transaction()
        conn.execute(
            """
            UPDATE repositories
            SET language = COALESCE(?, language),
                verified = ?,
                verified_at = ?,
                verification_message = ?,
                last_pipeline_path = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                normalize_language(language) if language else None,
                1 if verified else 0,
                verified_at,
                verification_message,
                pipeline_path,
                now,
                repo_id,
            ),
        )
        conn.commit()


def _normalize_tracked_branches(default_branch: str | None, tracked_branches: list[str] | None) -> list[str]:
    default = (default_branch or "main").strip() or "main"
    raw_branches = tracked_branches or [default, "develop"]
    normalized: list[str] = []
    seen: set[str] = set()

    for branch in [default, *raw_branches]:
        cleaned = (branch or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)

    if len(normalized) < 2:
        fallback = "develop" if default != "develop" else "release-candidate"
        if fallback not in seen:
            normalized.append(fallback)

    return normalized


_REPO_COLUMNS = """
    id, full_name, provider, local_path, default_branch, tracked_branches_json, pipeline_file, language,
    active, verified, verified_at, verification_message, last_pipeline_path,
    created_at, updated_at
"""


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
    trackedBranches: list[str] | None = None,
    pipelineFile: str = DEFAULT_PIPELINE_FILE,
    language: str | None = None,
    active: bool = True,
) -> dict:
    if not fullName:
        return {"ok": False, "reason": "fullName is required"}

    path_validation = _validate_local_repository_path(localPath)
    if not path_validation["ok"]:
        return path_validation

    pipeline_result = load_pipeline_definition(path_validation["absolute_path"], pipelineFile)
    pipeline_language = None
    if pipeline_result["ok"]:
        pipeline_language = pipeline_result["pipeline"].get("language")

    detected_language = infer_repository_language(
        path_validation["absolute_path"],
        pipeline_language or language,
    )

    existing = get_repository_by_full_name(fullName)
    normalized_tracked_branches = _normalize_tracked_branches(defaultBranch, trackedBranches)
    now = _now()
    repo_id = existing["id"] if existing else str(uuid.uuid4())
    created_at = existing["createdAt"] if existing else now
    verification_message = (
        "Repository updated. Verify again to confirm the latest pipeline configuration."
        if existing
        else "Repository registered. Run verification to validate the pipeline."
    )

    with db_lock:
        conn = transaction()
        conn.execute(
            """
            INSERT INTO repositories (
                id, full_name, provider, local_path, default_branch, tracked_branches_json, pipeline_file, language,
                active, verified, verified_at, verification_message, last_pipeline_path,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(full_name) DO UPDATE SET
                provider = excluded.provider,
                local_path = excluded.local_path,
                default_branch = excluded.default_branch,
                tracked_branches_json = excluded.tracked_branches_json,
                pipeline_file = excluded.pipeline_file,
                language = excluded.language,
                active = excluded.active,
                verified = excluded.verified,
                verified_at = excluded.verified_at,
                verification_message = excluded.verification_message,
                last_pipeline_path = excluded.last_pipeline_path,
                updated_at = excluded.updated_at
            """,
            (
                repo_id, fullName, provider,
                path_validation["absolute_path"],
                defaultBranch, json.dumps(normalized_tracked_branches), pipelineFile, detected_language,
                1 if active else 0,
                0,
                None,
                verification_message,
                None,
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
        _update_verification_state(
            repo_id,
            verified=False,
            verification_message=path_validation["reason"],
            verified_at=None,
            pipeline_path=None,
        )
        return path_validation

    pipeline_result = load_pipeline_definition(repository["localPath"], repository["pipelineFile"])
    if not pipeline_result["ok"]:
        _update_verification_state(
            repo_id,
            verified=False,
            verification_message=pipeline_result["reason"],
            verified_at=None,
            pipeline_path=None,
        )
        return {"ok": False, "reason": pipeline_result["reason"]}

    resolved_language = infer_repository_language(
        repository["localPath"],
        pipeline_result["pipeline"].get("language") or repository["language"],
    )
    verified_at = _now()
    _update_verification_state(
        repo_id,
        verified=True,
        verified_at=verified_at,
        verification_message=f"Verified successfully. {len(pipeline_result['pipeline']['steps'])} pipeline steps detected.",
        pipeline_path=pipeline_result["pipeline_path"],
        language=resolved_language,
    )
    repository = get_repository_by_id(repo_id)

    return {
        "ok": True,
        "repository": repository,
        "pipeline": pipeline_result["pipeline"],
        "pipelinePath": pipeline_result["pipeline_path"],
    }


def unverify_repository(repo_id: str) -> dict:
    repository = get_repository_by_id(repo_id)
    if not repository:
        return {"ok": False, "reason": "Repository not found"}

    _update_verification_state(
        repo_id,
        verified=False,
        verified_at=None,
        verification_message="Verification cleared. Verify again when you want this repository trusted by the dashboard.",
        pipeline_path=repository["lastPipelinePath"],
    )

    return {"ok": True, "repository": get_repository_by_id(repo_id)}


def delete_repository(repo_id: str) -> dict:
    repository = get_repository_by_id(repo_id)
    if not repository:
        return {"ok": False, "reason": "Repository not found"}

    with db_lock:
        conn = transaction()
        conn.execute("DELETE FROM repositories WHERE id = ?", (repo_id,))
        conn.commit()

    return {"ok": True, "repository": repository}
