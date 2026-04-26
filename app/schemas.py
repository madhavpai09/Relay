from __future__ import annotations

from pydantic import BaseModel


class RepositoryCreate(BaseModel):
    fullName: str
    provider: str = "github"
    localPath: str
    defaultBranch: str = "main"
    pipelineFile: str = ".relay.yml"
    active: bool = True


class JobStatusUpdate(BaseModel):
    status: str


class JobLogCreate(BaseModel):
    level: str = "info"
    message: str
