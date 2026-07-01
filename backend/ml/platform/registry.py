"""
Model registry — versioned artifacts on disk + a JSON metadata index, with an
'active' pointer per model. Solves the "rebuilt every boot" problem: train once,
persist, load the active version at startup. Postgres metadata mirroring is
added in db mode (Phase 9); the on-disk index is always authoritative locally.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
from typing import Any, Optional

import joblib

ARTIFACT_ROOT = pathlib.Path(__file__).resolve().parents[1] / "_artifacts"
_INDEX = ARTIFACT_ROOT / "index.json"


def _load_index() -> dict:
    if _INDEX.exists():
        return json.loads(_INDEX.read_text())
    return {}


def _save_index(idx: dict) -> None:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    _INDEX.write_text(json.dumps(idx, indent=2))


def save(obj: Any, name: str, version: str, metrics: Optional[dict] = None,
         status: str = "active") -> str:
    d = ARTIFACT_ROOT / name / version
    d.mkdir(parents=True, exist_ok=True)
    joblib.dump(obj, d / "model.joblib")
    meta = {"name": name, "version": version, "metrics": metrics or {},
            "status": status, "created_at": _dt.datetime.utcnow().isoformat()}
    (d / "metadata.json").write_text(json.dumps(meta, indent=2))
    idx = _load_index()
    entry = idx.setdefault(name, {"active": None, "versions": []})
    if version not in entry["versions"]:
        entry["versions"].append(version)
    if status == "active":
        entry["active"] = version
    _save_index(idx)
    return str(d)


def load(name: str, version: Optional[str] = None) -> Any:
    idx = _load_index()
    entry = idx.get(name)
    if not entry:
        raise FileNotFoundError(f"no registered model '{name}'")
    version = version or entry.get("active")
    if not version:
        raise FileNotFoundError(f"no active version for '{name}'")
    return joblib.load(ARTIFACT_ROOT / name / version / "model.joblib")


def promote(name: str, version: str) -> None:
    idx = _load_index()
    if name in idx and version in idx[name]["versions"]:
        idx[name]["active"] = version
        _save_index(idx)


def info(name: str) -> dict:
    return _load_index().get(name, {})
