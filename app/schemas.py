from __future__ import annotations

from pydantic import BaseModel


class RepositoryCreate(BaseModel):
    fullName: str
    provider: str = "github"
    localPath: str
    defaultBranch: str = "main"
    pipelineFile: str = ".relay.yml"
    language: str | None = None
    active: bool = True


class JobStatusUpdate(BaseModel):
    status: str


class JobLogCreate(BaseModel):
    level: str = "info"
    message: str


class SimulationStartRequest(BaseModel):
    minDelaySeconds: float = 2.0
    maxDelaySeconds: float = 6.0


class SimulationGenerateRequest(BaseModel):
    count: int = 1
    repositoryId: str | None = None
