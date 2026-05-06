from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class RunContext:
    run_id: str
    execution_mode: str
    started_at: str
    manifest_path: str
    reference_manifest_path: str | None = None


def build_run_context(
    config: dict[str, Any], execution_mode: str | None = None
) -> RunContext:
    mode = execution_mode or str(config.get("execution_mode") or "local")
    started_at = utc_now()
    prefix = str(config["run"]["id_prefix"])
    run_id = f"{prefix}-{mode}-{started_at.strftime('%Y%m%dT%H%M%SZ')}"
    manifest_dir = Path(str(config["run"]["manifest_dir"]))
    manifest_dir.mkdir(parents=True, exist_ok=True)
    reference_manifest = config["run"].get("reference_manifest_path")
    return RunContext(
        run_id=run_id,
        execution_mode=mode,
        started_at=to_iso(started_at),
        manifest_path=(manifest_dir / f"{run_id}.json").as_posix(),
        reference_manifest_path=str(reference_manifest) if reference_manifest else None,
    )


def write_run_manifest(context: RunContext, payload: dict[str, Any]) -> Path:
    manifest_path = Path(context.manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "run": asdict(context),
        "summary": payload,
    }
    manifest_path.write_text(json.dumps(body, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def build_storage_key(prefix: str, run_id: str, file_name: str) -> str:
    normalized_prefix = prefix.strip("/")
    return f"{normalized_prefix}/run_id={run_id}/{file_name}"

