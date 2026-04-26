from __future__ import annotations


def build_github_job_context(event: str | None, payload: dict) -> dict:
    repository = payload.get("repository", {}).get("full_name")

    if event == "push":
        return {
            "trigger_type": "push",
            "repository": repository,
            "ref": payload.get("ref"),
            "commit_sha": payload.get("after"),
            "pull_request_number": None,
            "action": None,
            "base_ref": None,
            "head_ref": None,
        }

    if event == "pull_request":
        pr = payload.get("pull_request", {})
        head = pr.get("head", {})
        base = pr.get("base", {})
        return {
            "trigger_type": "pull_request",
            "repository": repository,
            "ref": head.get("ref"),
            "commit_sha": head.get("sha"),
            "pull_request_number": payload.get("number") or pr.get("number"),
            "action": payload.get("action"),
            "base_ref": base.get("ref"),
            "head_ref": head.get("ref"),
        }

    return {
        "trigger_type": event or "unknown",
        "repository": repository,
        "ref": None,
        "commit_sha": None,
        "pull_request_number": None,
        "action": payload.get("action"),
        "base_ref": None,
        "head_ref": None,
    }
