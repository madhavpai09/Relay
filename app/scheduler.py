from __future__ import annotations

import threading

from .executor import run_job
from .jobs import add_job_log, get_job_by_id, get_next_queued_job, list_jobs, update_job_status


class Scheduler:
    def __init__(self) -> None:
        self.current_job_id: str | None = None
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._wake_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _recover_queue_on_startup(self) -> None:
        running_jobs = [job for job in list_jobs() if job["status"] == "running"]
        for job in running_jobs:
            add_job_log(job["id"], level="error", message="Master restarted while this job was running")
            update_job_status(job["id"], "failed")

    def _run_loop(self) -> None:
        self._recover_queue_on_startup()

        while not self._stop_event.is_set():
            if self.current_job_id is None:
                next_job = get_next_queued_job()
                if next_job is not None:
                    self.current_job_id = next_job["id"]
                    try:
                        run_job(next_job["id"])
                    except Exception as error:  # noqa: BLE001
                        add_job_log(next_job["id"], level="error", message=f"Scheduler crashed while running job: {error}")
                        update_job_status(next_job["id"], "failed")
                    finally:
                        self.current_job_id = None
                    continue

            self._wake_event.wait(timeout=1.0)
            self._wake_event.clear()

    def schedule_job(self, job_id: str) -> dict:
        job = get_job_by_id(job_id)
        if not job:
            return {"ok": False, "reason": "Job not found"}
        if job["status"] != "queued":
            return {
                "ok": False,
                "reason": f'Job must be queued before scheduling, current status is {job["status"]}',
            }

        self._wake_event.set()
        return {"ok": True, "job": job}

    def get_queue_snapshot(self) -> dict:
        jobs = list_jobs()
        queued_jobs = sorted(
            [job for job in jobs if job["status"] == "queued"],
            key=lambda job: job["createdAt"],
        )
        running_jobs = [job for job in jobs if job["status"] == "running"]

        return {
            "currentJobId": self.current_job_id,
            "queuedJobs": [
                {
                    "id": job["id"],
                    "repository": job["repository"],
                    "triggerType": job["triggerType"],
                    "createdAt": job["createdAt"],
                    "ref": job["ref"],
                }
                for job in queued_jobs
            ],
            "runningJobs": [
                {
                    "id": job["id"],
                    "repository": job["repository"],
                    "triggerType": job["triggerType"],
                    "startedAt": job["startedAt"],
                }
                for job in running_jobs
            ],
        }


scheduler = Scheduler()
