from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import RepositoryCreate
from ..services.repositories import (
    create_or_update_repository,
    delete_repository,
    get_repository_by_id,
    list_repositories,
    validate_repository,
)

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("")
def repositories_list() -> dict:
    return {"repositories": list_repositories()}


@router.get("/{repo_id}")
def repositories_get(repo_id: str):
    repository = get_repository_by_id(repo_id)
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repository


@router.post("", status_code=201)
def repositories_create(body: RepositoryCreate) -> dict:
    result = create_or_update_repository(**body.model_dump())
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["reason"])
    return {"message": "Repository saved", "repository": result["repository"]}


@router.post("/{repo_id}/validate")
def repositories_validate(repo_id: str) -> dict:
    result = validate_repository(repo_id)
    if not result["ok"]:
        raise HTTPException(
            status_code=404 if result["reason"] == "Repository not found" else 400,
            detail=result["reason"],
        )
    return {
        "message": "Repository configuration is valid",
        "repository": result["repository"],
        "pipelinePath": result["pipelinePath"],
        "pipeline": result["pipeline"],
    }


@router.delete("/{repo_id}")
def repositories_delete(repo_id: str) -> dict:
    result = delete_repository(repo_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result["reason"])
    return {"message": "Repository deleted", "repository": result["repository"]}
