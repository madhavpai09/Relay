from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import SimulationGenerateRequest, SimulationStartRequest
from ..services.simulation import traffic_simulator

router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.get("")
def simulation_status() -> dict:
    return traffic_simulator.snapshot()


@router.post("/start")
def simulation_start(body: SimulationStartRequest) -> dict:
    result = traffic_simulator.start(
        min_delay_seconds=body.minDelaySeconds,
        max_delay_seconds=body.maxDelaySeconds,
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["reason"])
    return {"message": "Simulation started", "simulation": result["status"]}


@router.post("/stop")
def simulation_stop() -> dict:
    result = traffic_simulator.stop()
    return {"message": "Simulation stopped", "simulation": result["status"]}


@router.post("/generate", status_code=201)
def simulation_generate(body: SimulationGenerateRequest) -> dict:
    result = traffic_simulator.generate_jobs(count=body.count, repository_id=body.repositoryId)
    if not result["ok"]:
        raise HTTPException(
            status_code=404 if result["reason"] == "Repository not found" else 400,
            detail=result["reason"],
        )
    return {
        "message": "Simulation jobs created",
        "jobs": result["jobs"],
        "coverage": result["coverage"],
    }
