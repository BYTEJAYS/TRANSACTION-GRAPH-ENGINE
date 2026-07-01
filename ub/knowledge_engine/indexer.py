"""
TGIE Knowledge Indexer (Phase 4 + 5).

Walks the entire TGIE workspace, selects text/code/doc files, splits them into
overlapping chunks, and tags each chunk with rich metadata (component, kind, path).
The chunks feed the embedding + vector-store pipeline so UB answers from RETRIEVED
project knowledge rather than model memory alone.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

# TGIE workspace root = two levels up from this file (ub/knowledge_engine/ -> TGIE/)
TGIE_ROOT = Path(__file__).resolve().parents[2]

# Directories we never index (artifacts, deps, the index itself, binaries)
SKIP_DIRS = {
    "node_modules", ".venv", "venv", ".git", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "dist", "build", ".next", ".turbo",
    "index", "_data", "backups", ".cache", "logs", "htmlcov", "egg-info",
}
# Extensions worth indexing as text
TEXT_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".txt", ".json", ".toml",
    ".yml", ".yaml", ".sh", ".command", ".css", ".html", ".env", ".ini",
    ".cfg", ".sql", ".dockerfile",
}
SPECIAL_NAMES = {"Dockerfile", "README", "DEPLOY", "INTEGRATION", "nixpacks", "railway"}
MAX_FILE_BYTES = 600_000  # skip anything larger (likely generated/data)


def classify_component(rel: str) -> str:
    """Map a repo-relative path to a TGIE ecosystem component."""
    p = rel.replace("\\", "/")
    if p.startswith("backend/blue_team"): return "Blue Team (in-engine)"
    if p.startswith("backend/ub_service"): return "UB Service (API)"
    if p.startswith("backend"): return "TGIE Core Backend"
    if p.startswith("frontend/ub_dashboard"): return "UB Dashboard"
    if p.startswith("frontend"): return "Frontend"
    if p.startswith("ub/knowledge_engine"): return "UB Knowledge Engine"
    if p.startswith("ub/ai_core"): return "UB AI Core"
    if p.startswith("ub/ollama_service"): return "UB Ollama Service"
    if p.startswith("ub"): return "UB (Universal Brain)"
    if p.startswith("blue_team"): return "Blue Team (BLING / Union Bank)"
    if p.startswith("red_team"): return "Red Team"
    if p.startswith("docs"): return "Documentation"
    if p.startswith("deployment"): return "Deployment"
    if p.startswith("monitoring"): return "Monitoring"
    if p.startswith("scripts"): return "Scripts"
    if p.startswith("configs"): return "Configuration"
    if p.startswith("datasets"): return "Datasets"
    if p.startswith("research"): return "Research"
    if p.startswith("tests"): return "Tests"
    return "Workspace"


def classify_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".py"}: return "python"
    if ext in {".ts", ".tsx", ".js", ".jsx"}: return "typescript/js"
    if ext == ".md": return "documentation"
    if ext == ".json": return "json"
    if ext in {".toml", ".yml", ".yaml", ".ini", ".cfg", ".env"}: return "config"
    if ext in {".sh", ".command"}: return "script"
    if ext in {".css", ".html"}: return "frontend-asset"
    if path.name in SPECIAL_NAMES or path.name.startswith("Dockerfile"): return "infra"
    return "text"


@dataclass
class Chunk:
    id: str
    path: str          # repo-relative
    component: str
    kind: str
    start_line: int
    end_line: int
    text: str

    def header(self) -> str:
        return f"[{self.component} · {self.path}:{self.start_line}-{self.end_line}]"


def _eligible(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXT:
        return True
    if path.name in SPECIAL_NAMES or path.name.startswith("Dockerfile"):
        return True
    return False


def iter_files(root: Path = TGIE_ROOT) -> List[Path]:
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for fn in filenames:
            fp = Path(dirpath) / fn
            if not _eligible(fp):
                continue
            try:
                if fp.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            files.append(fp)
    return files


def chunk_file(path: Path, root: Path = TGIE_ROOT,
               max_lines: int = 60, overlap: int = 12) -> List[Chunk]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return []
    if not text.strip():
        return []
    rel = str(path.relative_to(root))
    component = classify_component(rel)
    kind = classify_kind(path)
    lines = text.splitlines()
    chunks: List[Chunk] = []
    step = max(1, max_lines - overlap)
    for start in range(0, len(lines), step):
        window = lines[start:start + max_lines]
        body = "\n".join(window).strip()
        if not body:
            continue
        end = min(start + max_lines, len(lines))
        cid = hashlib.blake2b(f"{rel}:{start}".encode(), digest_size=8).hexdigest()
        chunks.append(Chunk(cid, rel, component, kind, start + 1, end, body))
        if end >= len(lines):
            break
    return chunks


def build_chunks(root: Path = TGIE_ROOT) -> List[Chunk]:
    """Full scan → list of chunks for the whole TGIE workspace."""
    all_chunks: List[Chunk] = []
    for fp in iter_files(root):
        all_chunks.extend(chunk_file(fp, root))
    return all_chunks


def chunks_to_records(chunks: List[Chunk]) -> List[Dict]:
    return [asdict(c) for c in chunks]


if __name__ == "__main__":
    cs = build_chunks()
    comps: Dict[str, int] = {}
    for c in cs:
        comps[c.component] = comps.get(c.component, 0) + 1
    print(f"TGIE_ROOT = {TGIE_ROOT}")
    print(f"files indexed: {len(set(c.path for c in cs))}, chunks: {len(cs)}")
    for comp, n in sorted(comps.items(), key=lambda x: -x[1]):
        print(f"  {comp:38s} {n}")
