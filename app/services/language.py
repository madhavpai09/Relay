from __future__ import annotations

from pathlib import Path


LANGUAGE_ALIASES = {
    "py": "python",
    "python": "python",
    "js": "node",
    "javascript": "node",
    "node": "node",
    "nodejs": "node",
    "ts": "node",
    "typescript": "node",
    "java": "java",
    "go": "go",
    "golang": "go",
    "generic": "generic",
}


def normalize_language(language: str | None) -> str:
    if not language:
        return "generic"
    return LANGUAGE_ALIASES.get(language.strip().lower(), "generic")


def infer_repository_language(workspace_path: str | Path, pipeline_language: str | None = None) -> str:
    normalized_pipeline_language = normalize_language(pipeline_language)
    if normalized_pipeline_language != "generic":
        return normalized_pipeline_language

    root = Path(workspace_path)

    if any((root / file_name).exists() for file_name in ("requirements.txt", "pyproject.toml", "setup.py", "Pipfile")):
        return "python"

    if any((root / file_name).exists() for file_name in ("package.json", "pnpm-lock.yaml", "yarn.lock")):
        return "node"

    if any((root / file_name).exists() for file_name in ("pom.xml", "build.gradle", "build.gradle.kts")):
        return "java"

    if (root / "go.mod").exists():
        return "go"

    return "generic"
