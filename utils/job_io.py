"""Shared job-state I/O for the background search and extraction managers.

Two guarantees the previous per-manager code lacked:

1. **Atomic writes** — state is written to a temp file in the same directory
   and then `os.replace`d into place, so a concurrent reader never sees a
   half-written file (which previously made `get_status` return None).
2. **Cooperative cancellation** — `request_cancel` sets a flag in the state
   file; the worker thread calls `is_cancelled` between work items and stops
   cleanly. Deleting the status file is no longer used as a cancel signal,
   which the daemon thread could not observe.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def write_atomic(path: Path, data: dict) -> None:
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)  # atomic on the same filesystem
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def patch(path: Path, **kwargs) -> None:
    data = read_json(path)
    if data is None:
        return
    data.update(kwargs)
    write_atomic(path, data)


def append_log(path: Path, line: str) -> None:
    data = read_json(path)
    if data is None:
        return
    data.setdefault("log", []).append(line)
    write_atomic(path, data)


def request_cancel(path: Path) -> None:
    data = read_json(path)
    if data is None:
        return
    data["cancel_requested"] = True
    write_atomic(path, data)


def is_cancelled(path: Path) -> bool:
    data = read_json(path)
    return bool(data and data.get("cancel_requested"))
