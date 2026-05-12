from __future__ import annotations

import threading

from .executor import run_job
from .jobs import (
    add_job_log,
    assign_job_to_worker,
    get_job_by_id,
    get_next_queued_job,
    list_jobs,
    update_job_status,
)
from .workers import worker_pool


class Scheduler:
    def __init__(self) -> None:
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._active_runs: dict[str, threading.Thread] = {}

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
        interrupted_jobs = [
            job for job in list_jobs() if job["status"] in {"assigned", "processing"}
        ]
        for job in interrupted_jobs:
            add_job_log(job["id"], level="error", message="Server restarted while this job was running")
            update_job_status(job["id"], "failed")

    def _pick_next_queued_job(self) -> dict | None:
        return get_next_queued_job()

    def _dispatch_available_jobs(self) -> bool:
        dispatched_any = False

        while not self._stop_event.is_set():
            next_job = self._pick_next_queued_job()
            if next_job is None:
                break

            reservation = worker_pool.reserve_worker_for_job(next_job)
            if not reservation["ok"]:
                break

            worker = reservation["worker"]
            assign_job_to_worker(next_job["id"], worker["id"], worker["name"])
            update_job_status(next_job["id"], "assigned")

            thread = threading.Thread(
                target=self._run_assigned_job,
                args=(worker["id"], next_job["id"]),
                daemon=True,
            )

            with self._lock:
                self._active_runs[worker["id"]] = thread

            thread.start()
            dispatched_any = True

        return dispatched_any

    def _run_assigned_job(self, worker_id: str, job_id: str) -> None:
        worker = worker_pool.get_worker(worker_id)
        try:
            if not worker:
                add_job_log(job_id, level="error", message=f"Worker {worker_id} disappeared before job start")
                update_job_status(job_id, "failed")
                return

            add_job_log(
                job_id,
                level="info",
                message=f'Worker {worker["name"]} accepted {get_job_by_id(job_id)["language"]} job',
            )
            run_job(job_id, worker=worker)
        except Exception as error:  # noqa: BLE001
            add_job_log(job_id, level="error", message=f"Scheduler crashed while running job: {error}")
            update_job_status(job_id, "failed")
        finally:
            worker_pool.release_worker(worker_id)
            with self._lock:
                self._active_runs.pop(worker_id, None)
            self._wake_event.set()

    def _run_loop(self) -> None:
        self._recover_queue_on_startup()

        while not self._stop_event.is_set():
            dispatched = self._dispatch_available_jobs()
            self._wake_event.wait(timeout=0.35 if dispatched else 1.0)
            self._wake_event.clear()

    def schedule_job(self, job_id: str) -> dict:
        job = get_job_by_id(job_id)
        if not job:
            return {"ok": False, "reason": "Job not found"}
        if job["status"] != "received":
            return {
                "ok": False,
                "reason": f'Job must be in "received" status before scheduling, current status is "{job["status"]}"',
            }

        update_job_status(job_id, "in_queue")
        self._wake_event.set()
        return {"ok": True, "job": get_job_by_id(job_id)}

    def get_queue_snapshot(self) -> dict:
        jobs = list_jobs()
        workers = worker_pool.list_workers()
        queued_jobs = sorted(
            [job for job in jobs if job["status"] == "in_queue"],
            key=lambda job: (-job["priorityScore"], job["createdAt"]),
        )
        active_jobs = [job for job in jobs if job["status"] in {"assigned", "processing"}]

        return {
            "summary": {
                "queuedCount": len(queued_jobs),
                "activeCount": len(active_jobs),
                "workerCount": len(workers),
                "busyWorkerCount": len([worker for worker in workers if worker["currentJobId"]]),
            },
            "queuedJobs": [
                {
                    "id": job["id"],
                    "repository": job["repository"],
                    "triggerType": job["triggerType"],
                    "language": job["language"],
                    "priorityLabel": job["priorityLabel"],
                    "priorityScore": job["priorityScore"],
                    "priorityReason": job["priorityReason"],
                    "createdAt": job["createdAt"],
                    "ref": job["ref"],
                }
                for job in queued_jobs
            ],
            "activeJobs": [
                {
                    "id": job["id"],
                    "repository": job["repository"],
                    "triggerType": job["triggerType"],
                    "language": job["language"],
                    "priorityLabel": job["priorityLabel"],
                    "priorityScore": job["priorityScore"],
                    "status": job["status"],
                    "assignedWorkerId": job["assignedWorkerId"],
                    "assignedWorkerName": job["assignedWorkerName"],
                    "startedAt": job["startedAt"],
                }
                for job in active_jobs
            ],
            "workers": workers,
        }


scheduler = Scheduler()
