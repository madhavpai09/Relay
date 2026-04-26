from __future__ import annotations


def should_create_job(event: str | None, payload: dict) -> dict:
    if event == "push":
        return {
            "should_create": True,
            "reason": "Push events should trigger CI",
        }

    if event == "pull_request":
        action = payload.get("action")
        allowed_actions = {"opened", "synchronize", "reopened"}

        if action in allowed_actions:
            return {
                "should_create": True,
                "reason": f'Pull request action "{action}" should trigger CI',
            }

        return {
            "should_create": False,
            "reason": f'Pull request action "{action}" does not trigger CI',
        }

    return {
        "should_create": False,
        "reason": f'Event "{event}" does not trigger CI jobs',
    }
