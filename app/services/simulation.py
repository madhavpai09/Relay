from __future__ import annotations

from dataclasses import dataclass
import random
import threading
import time
import uuid

from .jobs import create_job
from .repositories import get_repository_by_id, list_repositories
from .scheduler import scheduler


@dataclass
class SimulationConfig:
    min_delay_seconds: float = 2.0
    max_delay_seconds: float = 6.0


class TrafficSimulator:
    def __init__(self) -> None:
        self._config = SimulationConfig()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self, min_delay_seconds: float = 2.0, max_delay_seconds: float = 6.0) -> dict:
        if min_delay_seconds <= 0 or max_delay_seconds <= 0:
            return {"ok": False, "reason": "Delay values must be positive"}
        if min_delay_seconds > max_delay_seconds:
            return {"ok": False, "reason": "minDelaySeconds must be less than or equal to maxDelaySeconds"}

        with self._lock:
            self._config = SimulationConfig(
                min_delay_seconds=min_delay_seconds,
                max_delay_seconds=max_delay_seconds,
            )
            if self._thread and self._thread.is_alive():
                return {"ok": True, "status": self.snapshot()}

            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

        return {"ok": True, "status": self.snapshot()}

    def stop(self) -> dict:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        return {"ok": True, "status": self.snapshot()}

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "running": bool(self._thread and self._thread.is_alive() and not self._stop_event.is_set()),
                "minDelaySeconds": self._config.min_delay_seconds,
                "maxDelaySeconds": self._config.max_delay_seconds,
            }

    def _active_repositories(self) -> list[dict]:
        return [repo for repo in list_repositories() if repo["active"]]

    def _build_payload(self, repository: dict, event: str) -> tuple[str, dict]:
        commit_sha = uuid.uuid4().hex[:12]
        branch = repository["defaultBranch"] or "main"

        if event == "pull_request":
            pr_number = random.randint(1, 50)
            feature_branch = f"feature/sim-{uuid.uuid4().hex[:6]}"
            payload = {
                "action": random.choice(["opened", "synchronize", "reopened"]),
                "number": pr_number,
                "repository": {"full_name": repository["fullName"]},
                "pull_request": {
                    "number": pr_number,
                    "head": {"ref": feature_branch, "sha": commit_sha},
                    "base": {"ref": branch},
                },
            }
            return commit_sha, payload

        payload = {
            "ref": f"refs/heads/{branch}",
            "after": commit_sha,
            "repository": {"full_name": repository["fullName"]},
        }
        return commit_sha, payload

    def generate_jobs(self, count: int = 1, repository_id: str | None = None) -> dict:
        if count <= 0:
            return {"ok": False, "reason": "count must be greater than 0"}

        if repository_id:
            repository = get_repository_by_id(repository_id)
            if not repository:
                return {"ok": False, "reason": "Repository not found"}
            repositories = [repository]
        else:
            repositories = self._active_repositories()

        if not repositories:
            return {"ok": False, "reason": "No active repositories are registered for simulation"}

        created_jobs = []
        for _ in range(count):
            repository = random.choice(repositories)
            event = random.choices(["push", "pull_request"], weights=[0.7, 0.3], k=1)[0]
            commit_sha, payload = self._build_payload(repository, event)

            job = create_job(
                event=event,
                delivery_id=f"sim-{uuid.uuid4()}",
                repository=repository["fullName"],
                trigger_type=event,
                language=repository["language"],
                ref=payload.get("ref") or payload.get("pull_request", {}).get("head", {}).get("ref"),
                commit_sha=commit_sha,
                pull_request_number=payload.get("number"),
                action=payload.get("action"),
                base_ref=payload.get("pull_request", {}).get("base", {}).get("ref"),
                head_ref=payload.get("pull_request", {}).get("head", {}).get("ref"),
                workspace_path=repository["localPath"],
                pipeline_file=repository["pipelineFile"],
                payload=payload,
            )
            scheduler.schedule_job(job["id"])
            created_jobs.append(job)

        return {"ok": True, "jobs": created_jobs}

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            delay = random.uniform(
                self._config.min_delay_seconds,
                self._config.max_delay_seconds,
            )
            time.sleep(delay)
            if self._stop_event.is_set():
                break
            burst_size = random.randint(1, 2)
            self.generate_jobs(count=burst_size)


traffic_simulator = TrafficSimulator()
