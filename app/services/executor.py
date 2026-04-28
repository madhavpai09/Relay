from __future__ import annotations

from subprocess import Popen, PIPE
from threading import Thread
import random
import time

from .jobs import add_job_log, get_job_by_id, update_job_status
from .pipeline import load_pipeline_definition


def _stream_output(job_id: str, pipe, level: str) -> None:
    for line in iter(pipe.readline, ""):
        message = line.strip()
        if message:
            add_job_log(job_id, level=level, message=message)
    pipe.close()


def run_job(job_id: str, worker: dict | None = None) -> dict:
    running_result = update_job_status(job_id, "processing")
    if not running_result["ok"]:
        return running_result

    if worker:
        add_job_log(
            job_id,
            level="info",
            message=f'Worker {worker["name"]} picked up job for {worker["supportedLanguages"]}',
        )
        startup_delay = round(random.uniform(0.15, 0.75) * worker.get("speedMultiplier", 1.0), 2)
        add_job_log(job_id, level="info", message=f"Worker startup delay: {startup_delay}s")
        time.sleep(startup_delay)
    else:
        add_job_log(job_id, level="info", message="Executor picked up job from queue")

    job = get_job_by_id(job_id)
    workspace_path = job["workspacePath"]
    pipeline_file = job["pipelineFile"]

    add_job_log(job_id, level="info", message=f"Using workspace {workspace_path}")

    pipeline_result = load_pipeline_definition(workspace_path, pipeline_file)
    if not pipeline_result["ok"]:
        add_job_log(job_id, level="error", message=f'Failed to load pipeline: {pipeline_result["reason"]}')
        return update_job_status(job_id, "failed")

    add_job_log(job_id, level="info", message=f'Loaded pipeline from {pipeline_result["pipeline_path"]}')

    for step in pipeline_result["pipeline"]["steps"]:
        add_job_log(job_id, level="info", message=f'Starting step "{step["name"]}"')
        add_job_log(job_id, level="info", message=f'Command: {step["command"]}')

        if worker:
            jitter = round(random.uniform(0.05, 0.4) * worker.get("speedMultiplier", 1.0), 2)
            add_job_log(job_id, level="info", message=f'Worker {worker["name"]} warmup jitter: {jitter}s')
            time.sleep(jitter)

        try:
            process = Popen(
                step["command"],
                cwd=workspace_path,
                shell=True,
                text=True,
                stdout=PIPE,
                stderr=PIPE,
            )
        except Exception as error:  # noqa: BLE001
            add_job_log(job_id, level="error", message=f'Step "{step["name"]}" crashed before completion: {error}')
            return update_job_status(job_id, "failed")

        stdout_thread = Thread(target=_stream_output, args=(job_id, process.stdout, "info"), daemon=True)
        stderr_thread = Thread(target=_stream_output, args=(job_id, process.stderr, "error"), daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        code = process.wait()
        stdout_thread.join()
        stderr_thread.join()

        if code != 0:
            add_job_log(job_id, level="error", message=f'Step "{step["name"]}" failed with exit code {code}')
            return update_job_status(job_id, "failed")

        add_job_log(job_id, level="info", message=f'Step "{step["name"]}" completed successfully')

    add_job_log(job_id, level="info", message="All pipeline steps completed")
    return update_job_status(job_id, "processed")
