from __future__ import annotations

from datetime import datetime, timezone
import random
import threading


WORKER_BLUEPRINTS = [
    {
        "id": "worker-python-1",
        "name": "Python Worker 1",
        "supportedLanguages": ["python", "generic"],
        "speedMultiplier": 0.85,
    },
    {
        "id": "worker-python-2",
        "name": "Python Worker 2",
        "supportedLanguages": ["python", "generic"],
        "speedMultiplier": 1.1,
    },
    {
        "id": "worker-node-1",
        "name": "Node Worker 1",
        "supportedLanguages": ["node", "generic"],
        "speedMultiplier": 0.95,
    },
    {
        "id": "worker-universal-1",
        "name": "Universal Worker 1",
        "supportedLanguages": ["python", "node", "java", "go", "generic"],
        "speedMultiplier": 1.2,
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkerPool:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._workers = {
            blueprint["id"]: {
                **blueprint,
                "currentJobId": None,
                "jobsCompleted": 0,
                "lastAssignedAt": None,
                "lastCompletedAt": None,
            }
            for blueprint in WORKER_BLUEPRINTS
        }

    def list_workers(self) -> list[dict]:
        with self._lock:
            return [dict(worker) for worker in self._workers.values()]

    def get_worker(self, worker_id: str) -> dict | None:
        with self._lock:
            worker = self._workers.get(worker_id)
            return dict(worker) if worker else None

    def _can_accept(self, worker: dict, language: str) -> bool:
        return worker["currentJobId"] is None and language in worker["supportedLanguages"]

    def reserve_worker_for_job(self, job: dict) -> dict:
        language = job.get("language") or "generic"

        with self._lock:
            candidates = [
                worker
                for worker in self._workers.values()
                if self._can_accept(worker, language)
            ]

            if not candidates and language != "generic":
                candidates = [
                    worker
                    for worker in self._workers.values()
                    if self._can_accept(worker, "generic")
                ]

            if not candidates:
                return {
                    "ok": False,
                    "reason": f'No available worker can accept language "{language}" right now',
                }

            def _score(worker: dict) -> float:
                exact_match_penalty = 0.0 if language in worker["supportedLanguages"] else 0.8
                return worker["jobsCompleted"] + exact_match_penalty + random.uniform(0.0, 0.35)

            selected = min(candidates, key=_score)
            selected["currentJobId"] = job["id"]
            selected["lastAssignedAt"] = _now()

            return {"ok": True, "worker": dict(selected)}

    def release_worker(self, worker_id: str) -> None:
        with self._lock:
            worker = self._workers.get(worker_id)
            if not worker:
                return
            worker["currentJobId"] = None
            worker["jobsCompleted"] += 1
            worker["lastCompletedAt"] = _now()


worker_pool = WorkerPool()
