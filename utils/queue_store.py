"""Persist search queue text per project to a file so it survives page reloads."""

import json
from pathlib import Path

STORE_DIR = Path("search_jobs")
STORE_DIR.mkdir(exist_ok=True)


def _path(project_id: int) -> Path:
    return STORE_DIR / f"queues_{project_id}.json"


def load_queues(project_id: int) -> dict:
    p = _path(project_id)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {"ls": "", "ca": ""}


def save_ls_queue(project_id: int, text: str):
    data = load_queues(project_id)
    data["ls"] = text
    _path(project_id).write_text(json.dumps(data))


def save_ca_queue(project_id: int, text: str):
    data = load_queues(project_id)
    data["ca"] = text
    _path(project_id).write_text(json.dumps(data))
