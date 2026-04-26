from __future__ import annotations

from pathlib import Path

from .config import DEFAULT_PIPELINE_FILE


def _apply_key_value(target: dict, line: str) -> None:
    if ":" not in line:
        raise ValueError(f'Invalid pipeline line: "{line}"')

    key, value = line.split(":", 1)
    key = key.strip()
    value = value.strip()

    if not key:
        raise ValueError(f'Missing key in pipeline line: "{line}"')

    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]

    target[key] = value


def parse_relay_yaml(content: str) -> dict:
    lines = content.splitlines()
    steps: list[dict] = []
    in_steps_section = False
    current_step: dict | None = None

    for raw_line in lines:
        trimmed = raw_line.strip()

        if not trimmed or trimmed.startswith("#"):
            continue

        if not in_steps_section:
            if trimmed != "steps:":
                raise ValueError("Pipeline file must start with a steps: section")
            in_steps_section = True
            continue

        if trimmed.startswith("- "):
            if current_step:
                steps.append(current_step)
            current_step = {}
            remainder = trimmed[2:].strip()
            if remainder:
                _apply_key_value(current_step, remainder)
            continue

        if current_step is None:
            raise ValueError(f'Step property found before step declaration: "{trimmed}"')

        _apply_key_value(current_step, trimmed)

    if current_step:
        steps.append(current_step)

    if not steps:
        raise ValueError("Pipeline must contain at least one step")

    for step in steps:
        if not step.get("name") or not step.get("command"):
            raise ValueError("Each pipeline step must contain both name and command")

    return {"steps": steps}


def load_pipeline_definition(workspace_path: str | Path, pipeline_file: str = DEFAULT_PIPELINE_FILE) -> dict:
    pipeline_path = Path(workspace_path) / pipeline_file

    if not pipeline_path.exists():
        return {
            "ok": False,
            "reason": f"Pipeline file not found at {pipeline_path}",
        }

    try:
        pipeline = parse_relay_yaml(pipeline_path.read_text(encoding="utf8"))
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "reason": str(error),
        }

    return {
        "ok": True,
        "pipeline_path": str(pipeline_path),
        "pipeline": pipeline,
    }
