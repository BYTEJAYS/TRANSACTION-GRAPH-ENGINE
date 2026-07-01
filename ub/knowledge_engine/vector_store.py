"""
Local vector database for UB (Phase 4).

Deliberately dependency-light: vectors are stored as a NumPy array on disk
(`index/vectors.npy`) alongside chunk metadata (`index/chunks.jsonl`) and a small
`index/meta.json`. Retrieval is exact cosine similarity — more than fast enough for
a single project's worth of chunks (thousands), and zero external services.

Falls back to a pure-Python cosine if NumPy is unavailable.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np
    _HAVE_NUMPY = True
except Exception:  # pragma: no cover
    _HAVE_NUMPY = False

INDEX_DIR = Path(__file__).resolve().parent / "index"


class VectorStore:
    def __init__(self, index_dir: Path = INDEX_DIR):
        self.dir = Path(index_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.vectors_path = self.dir / "vectors.npy"
        self.chunks_path = self.dir / "chunks.jsonl"
        self.meta_path = self.dir / "meta.json"
        self._vectors = None              # np.ndarray (N, D) or list[list[float]]
        self._chunks: List[Dict] = []
        self._meta: Dict = {}

    # ── persistence ─────────────────────────────────────────────────────────
    def save(self, vectors, chunks: List[Dict], meta: Dict) -> None:
        if _HAVE_NUMPY:
            arr = np.asarray(vectors, dtype="float32")
            # L2-normalize once so retrieval is a plain dot product
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            np.save(self.vectors_path, arr / norms)
        else:  # pragma: no cover
            self.vectors_path.with_suffix(".json").write_text(json.dumps(vectors))
        with self.chunks_path.open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")
        self.meta_path.write_text(json.dumps(meta, indent=2))
        self._vectors, self._chunks, self._meta = None, [], {}  # force reload

    def load(self) -> bool:
        if not self.chunks_path.exists():
            return False
        if _HAVE_NUMPY and self.vectors_path.exists():
            self._vectors = np.load(self.vectors_path)
        elif self.vectors_path.with_suffix(".json").exists():  # pragma: no cover
            self._vectors = json.loads(self.vectors_path.with_suffix(".json").read_text())
        else:
            return False
        self._chunks = [json.loads(l) for l in self.chunks_path.read_text().splitlines() if l.strip()]
        self._meta = json.loads(self.meta_path.read_text()) if self.meta_path.exists() else {}
        return True

    @property
    def meta(self) -> Dict:
        if not self._meta and self.meta_path.exists():
            self._meta = json.loads(self.meta_path.read_text())
        return self._meta

    def ready(self) -> bool:
        return self.chunks_path.exists() and (
            self.vectors_path.exists() or self.vectors_path.with_suffix(".json").exists())

    # ── retrieval ─────────────────────────────────────────────────────────
    def search(self, query_vec: List[float], k: int = 6,
               component: Optional[str] = None) -> List[Tuple[float, Dict]]:
        if self._vectors is None and not self.load():
            return []
        if _HAVE_NUMPY:
            q = np.asarray(query_vec, dtype="float32")
            qn = q / (np.linalg.norm(q) or 1.0)
            sims = self._vectors @ qn          # vectors are pre-normalized
            order = np.argsort(-sims)
            results: List[Tuple[float, Dict]] = []
            for i in order:
                ch = self._chunks[int(i)]
                if component and ch.get("component") != component:
                    continue
                results.append((float(sims[int(i)]), ch))
                if len(results) >= k:
                    break
            return results
        # pure-python fallback
        def cos(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a)) or 1.0
            nb = math.sqrt(sum(y * y for y in b)) or 1.0
            return dot / (na * nb)
        scored = [(cos(query_vec, v), self._chunks[i]) for i, v in enumerate(self._vectors)]
        scored.sort(key=lambda x: -x[0])
        if component:
            scored = [s for s in scored if s[1].get("component") == component]
        return scored[:k]
