from __future__ import annotations

from dataclasses import dataclass
import random
import threading
import time
import uuid

from .jobs import create_job
from .priority import compute_job_priority
from .repositories import get_repository_by_id, list_repositories
from .scheduler import scheduler


@dataclass
class SimulationConfig:
    min_delay_seconds: float = 2.0
    max_delay_seconds: float = 6.0


class TrafficSimulator:
    MINIMUM_REPOSITORIES = 3
    MINIMUM_BRANCHES_PER_REPOSITORY = 2

    def __init__(self) -> None:
        self._config = SimulationConfig()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._coverage_cursor = 0

    def start(self, min_delay_seconds: float = 2.0, max_delay_seconds: float = 6.0) -> dict:
        if min_delay_seconds <= 0 or max_delay_seconds <= 0:
            return {"ok": False, "reason": "Delay values must be positive"}
        if min_delay_seconds > max_delay_seconds:
            return {"ok": False, "reason": "minDelaySeconds must be less than or equal to maxDelaySeconds"}

        readiness = self._minimum_coverage_status()
        if not readiness["ok"]:
            return readiness

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
        readiness = self._minimum_coverage_status()
        with self._lock:
            return {
                "running": bool(self._thread and self._thread.is_alive() and not self._stop_event.is_set()),
                "minDelaySeconds": self._config.min_delay_seconds,
                "maxDelaySeconds": self._config.max_delay_seconds,
                "coverage": readiness["coverage"],
                "readinessReason": None if readiness["ok"] else readiness["reason"],
            }

    def _active_repositories(self) -> list[dict]:
        return [repo for repo in list_repositories() if repo["active"]]

    def _eligible_repositories(self) -> list[dict]:
        return [
            repo
            for repo in self._active_repositories()
            if len(repo.get("trackedBranches") or []) >= self.MINIMUM_BRANCHES_PER_REPOSITORY
        ]

    def _minimum_coverage_status(self) -> dict:
        eligible_repositories = self._eligible_repositories()
        selected_repositories = eligible_repositories[: self.MINIMUM_REPOSITORIES]
        covered_branches = sum(
            len(repo["trackedBranches"][: self.MINIMUM_BRANCHES_PER_REPOSITORY])
            for repo in selected_repositories
        )
        meets_requirement = (
            len(selected_repositories) >= self.MINIMUM_REPOSITORIES
            and covered_branches >= self.MINIMUM_REPOSITORIES * self.MINIMUM_BRANCHES_PER_REPOSITORY
        )
        coverage = {
            "meetsMinimum": meets_requirement,
            "eligibleRepositoryCount": len(eligible_repositories),
            "requiredRepositoryCount": self.MINIMUM_REPOSITORIES,
            "requiredBranchesPerRepository": self.MINIMUM_BRANCHES_PER_REPOSITORY,
            "coveredBranchCount": covered_branches,
            "requiredBranchCount": self.MINIMUM_REPOSITORIES * self.MINIMUM_BRANCHES_PER_REPOSITORY,
            "repositories": [
                {
                    "fullName": repo["fullName"],
                    "trackedBranches": repo["trackedBranches"][: self.MINIMUM_BRANCHES_PER_REPOSITORY],
                }
                for repo in selected_repositories
            ],
        }
        if meets_requirement:
            return {"ok": True, "coverage": coverage}

        return {
            "ok": False,
            "reason": (
                "Simulation requires at least 3 active repositories with at least 2 tracked branches each "
                "so Relay can send git pushes across 6 distinct branches."
            ),
            "coverage": coverage,
        }

    def _build_push_payload(self, repository: dict, branch: str) -> tuple[str, dict]:
        commit_sha = uuid.uuid4().hex[:12]
        commit_count = random.randint(1, 4)
        commits = []
        for index in range(commit_count):
            commits.append(
                {
                    "id": uuid.uuid4().hex[:7],
                    "message": f"Simulated commit {index + 1} for {branch}",
                    "author": {"name": f"relay-bot-{index + 1}", "email": f"relay-bot-{index + 1}@example.com"},
                }
            )

        payload = {
            "ref": f"refs/heads/{branch}",
            "after": commit_sha,
            "repository": {"full_name": repository["fullName"]},
            "commits": commits,
            "head_commit": commits[-1],
        }
        return commit_sha, payload

    def _build_pull_request_payload(self, repository: dict) -> tuple[str, dict]:
        commit_sha = uuid.uuid4().hex[:12]
        branch = repository["defaultBranch"] or "main"
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

    def _coverage_push_targets(self) -> list[tuple[dict, str]]:
        readiness = self._minimum_coverage_status()
        if not readiness["ok"]:
            return []

        selected_repositories = self._eligible_repositories()[: self.MINIMUM_REPOSITORIES]
        targets: list[tuple[dict, str]] = []
        for repository in selected_repositories:
            for branch in repository["trackedBranches"][: self.MINIMUM_BRANCHES_PER_REPOSITORY]:
                targets.append((repository, branch))
        return targets

    def _next_coverage_target(self) -> tuple[dict, str] | None:
        targets = self._coverage_push_targets()
        if not targets:
            return None

        with self._lock:
            target = targets[self._coverage_cursor % len(targets)]
            self._coverage_cursor = (self._coverage_cursor + 1) % len(targets)
        return target

    def generate_jobs(self, count: int = 1, repository_id: str | None = None) -> dict:
        if count <= 0:
            return {"ok": False, "reason": "count must be greater than 0"}

        if repository_id:
            repository = get_repository_by_id(repository_id)
            if not repository:
                return {"ok": False, "reason": "Repository not found"}
            repositories = [repository]
        else:
            readiness = self._minimum_coverage_status()
            if not readiness["ok"]:
                return readiness
            repositories = self._active_repositories()

        if not repositories:
            return {"ok": False, "reason": "No active repositories are registered for simulation"}

        created_jobs = []
        for _ in range(count):
            force_push_target = None if repository_id else self._next_coverage_target()

            if force_push_target:
                repository, branch = force_push_target
                event = "push"
                commit_sha, payload = self._build_push_payload(repository, branch)
                ref = payload["ref"]
                base_ref = None
                head_ref = None
            else:
                repository = random.choice(repositories)
                event = random.choices(["push", "pull_request"], weights=[0.75, 0.25], k=1)[0]
                if event == "push":
                    branch = random.choice(repository["trackedBranches"])
                    commit_sha, payload = self._build_push_payload(repository, branch)
                    ref = payload["ref"]
                    base_ref = None
                    head_ref = None
                else:
                    commit_sha, payload = self._build_pull_request_payload(repository)
                    ref = payload["pull_request"]["head"]["ref"]
                    base_ref = payload["pull_request"]["base"]["ref"]
                    head_ref = payload["pull_request"]["head"]["ref"]

            priority = compute_job_priority(
                trigger_type=event,
                ref=ref,
                payload=payload,
                repository=repository,
            )

            job = create_job(
                event=event,
                delivery_id=f"sim-{uuid.uuid4()}",
                repository=repository["fullName"],
                trigger_type=event,
                language=repository["language"],
                ref=ref,
                commit_sha=commit_sha,
                pull_request_number=payload.get("number"),
                action=payload.get("action"),
                base_ref=base_ref,
                head_ref=head_ref,
                workspace_path=repository["localPath"],
                pipeline_file=repository["pipelineFile"],
                priority_label=priority["label"],
                priority_score=priority["score"],
                priority_reason=priority["reason"],
                payload=payload,
            )
            scheduler.schedule_job(job["id"])
            created_jobs.append(job)

        return {"ok": True, "jobs": created_jobs, "coverage": self.snapshot()["coverage"]}

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
