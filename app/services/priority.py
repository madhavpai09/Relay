from __future__ import annotations

from typing import Any


def normalize_branch_name(ref: str | None) -> str | None:
    if not ref:
        return None
    if ref.startswith("refs/heads/"):
        return ref.removeprefix("refs/heads/")
    return ref


def _branch_priority(branch: str | None, tracked_branches: list[str], default_branch: str) -> tuple[int, str]:
    if not branch:
        return 10, "branch missing from payload"

    if branch == default_branch:
        return 90, f"push targets the default branch ({default_branch})"

    lowered = branch.lower()
    if lowered.startswith("hotfix/") or lowered.startswith("release/"):
        return 75, "push targets a release or hotfix branch"

    if branch in tracked_branches:
        return 55, "push targets a tracked integration branch"

    if lowered in {"develop", "development", "staging", "stage"}:
        return 45, "push targets a shared pre-production branch"

    return 25, "push targets a feature or ad-hoc branch"


def compute_job_priority(
    *,
    trigger_type: str,
    ref: str | None,
    payload: dict[str, Any],
    repository: dict | None = None,
) -> dict[str, Any]:
    branch = normalize_branch_name(ref)
    default_branch = (
        repository.get("defaultBranch")
        if repository and repository.get("defaultBranch")
        else "main"
    )
    tracked_branches = repository.get("trackedBranches") if repository else None
    tracked_branches = tracked_branches or [default_branch]

    if trigger_type == "push":
        branch_score, branch_reason = _branch_priority(branch, tracked_branches, default_branch)
        commit_count = len(payload.get("commits") or [])
        distinct_authors = len(
            {
                (commit.get("author") or {}).get("email")
                for commit in (payload.get("commits") or [])
                if (commit.get("author") or {}).get("email")
            }
        )
        score = 200 + branch_score + min(commit_count, 20) + min(distinct_authors * 3, 9)
        return {
            "label": (
                "critical"
                if branch_score >= 90
                else "high"
                if branch_score >= 75
                else "normal"
            ),
            "score": score,
            "reason": (
                f"{branch_reason}; commit batch size={commit_count}; "
                f"distinct authors={distinct_authors}"
            ),
        }

    if trigger_type == "pull_request":
        action = payload.get("action") or "updated"
        action_score = {
            "opened": 145,
            "reopened": 140,
            "synchronize": 135,
        }.get(action, 125)
        return {
            "label": "normal",
            "score": action_score,
            "reason": f"pull request event ({action}) queued below direct branch pushes",
        }

    return {
        "label": "low",
        "score": 50,
        "reason": f"fallback priority for unsupported trigger type ({trigger_type})",
    }
