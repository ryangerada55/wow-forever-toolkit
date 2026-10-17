"""The state file: the last build patchwatch has seen on each branch."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA = 1


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not Path(path).is_file():
        return {"schema": SCHEMA, "branches": {}}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read state file {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("branches"), dict):
        raise ValueError(f"state file {path} has an unexpected format")
    return data


def save_state(path: Path, state: Dict[str, Any]) -> None:
    """Write atomically (os.replace works on Windows, macOS and Linux)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["schema"] = SCHEMA
    state["updated"] = now_utc()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
