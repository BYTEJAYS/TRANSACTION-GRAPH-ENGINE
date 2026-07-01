"""
Knowledge Engine orchestrator (Phase 4 + 11).

Ties together: indexer (scan/chunk) → Ollama embeddings → VectorStore (persist) and
provides retrieval + context-block construction for UB. Tracks a file manifest so the
index can detect when the codebase changed and re-build (self-updating knowledge).
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .indexer import TGIE_ROOT, build_chunks, iter_files, chunks_to_records
from .vector_store import VectorStore, INDEX_DIR

# ollama_service is a sibling package under ub/
try:
    from ..ollama_service import OllamaClient
except ImportError:  # allow running as a top-level module too
    from ub.ollama_service import OllamaClient  # type: ignore


def _manifest(root: Path = TGIE_ROOT) -> Dict[str, str]:
    """path -> 'mtime:size' signature for cheap change detection."""
    m: Dict[str, str] = {}
    for fp in iter_files(root):
        try:
            st = fp.stat()
            m[str(fp.relative_to(root))] = f"{int(st.st_mtime)}:{st.st_size}"
        except OSError:
            continue
    return m


def _manifest_hash(m: Dict[str, str]) -> str:
    blob = "\n".join(f"{k}={v}" for k, v in sorted(m.items()))
    return hashlib.blake2b(blob.encode(), digest_size=12).hexdigest()


class KnowledgeEngine:
    def __init__(self, client: Optional[OllamaClient] = None, index_dir: Path = INDEX_DIR):
        self.client = client or OllamaClient()
        self.store = VectorStore(index_dir)

    # ── build / refresh ─────────────────────────────────────────────────────
    MAX_EMBED_CHARS = 6000  # keep each chunk well within the embed model's context

    def build(self, *, verbose: bool = True) -> Dict:
        chunks = build_chunks()
        all_records = chunks_to_records(chunks)
        if verbose:
            print(f"[knowledge_engine] embedding {len(all_records)} chunks "
                  f"with '{self.client.embed_model}' ...")
        vectors: List[List[float]] = []
        records: List[Dict] = []  # only chunks that embedded OK (kept aligned with vectors)
        skipped = 0
        t0 = time.time()
        for i, rec in enumerate(all_records):
            # embed the header + body so component/path context is part of the signal
            text = f"{rec['component']} | {rec['path']}\n{rec['text']}"[: self.MAX_EMBED_CHARS]
            try:
                vec = self.client.embed(text)
            except Exception:
                # one retry on a much shorter slice, then skip the chunk entirely
                try:
                    vec = self.client.embed(text[:1500])
                except Exception:
                    skipped += 1
                    if verbose:
                        print(f"  ! skipped {rec['path']}:{rec['start_line']} (embed error)")
                    continue
            vectors.append(vec)
            records.append(rec)
            if verbose and (i + 1) % 250 == 0:
                print(f"  {i + 1}/{len(all_records)} (kept {len(records)}, skipped {skipped})")
        man = _manifest()
        meta = {
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "build_seconds": round(time.time() - t0, 1),
            "chunk_count": len(records),
            "file_count": len(set(r["path"] for r in records)),
            "embed_model": self.client.embed_model,
            "chat_model": self.client.model,
            "manifest_hash": _manifest_hash(man),
            "manifest": man,
            "components": self._component_counts(records),
        }
        self.store.save(vectors, records, meta)
        if verbose:
            print(f"[knowledge_engine] indexed {meta['file_count']} files / "
                  f"{meta['chunk_count']} chunks in {meta['build_seconds']}s → {self.store.dir}")
        return meta

    @staticmethod
    def _component_counts(records: List[Dict]) -> Dict[str, int]:
        c: Dict[str, int] = {}
        for r in records:
            c[r["component"]] = c.get(r["component"], 0) + 1
        return c

    # ── self-updating (Phase 11) ─────────────────────────────────────────────
    def is_stale(self) -> bool:
        """True if the workspace changed since the index was built."""
        if not self.store.ready():
            return True
        stored = self.store.meta.get("manifest_hash")
        return stored != _manifest_hash(_manifest())

    def refresh_if_stale(self, *, verbose: bool = False) -> bool:
        if self.is_stale():
            self.build(verbose=verbose)
            return True
        return False

    # ── retrieval ─────────────────────────────────────────────────────────
    def retrieve(self, query: str, k: int = 6,
                 component: Optional[str] = None) -> List[Tuple[float, Dict]]:
        qv = self.client.embed(query)
        return self.store.search(qv, k=k, component=component)

    def context_block(self, query: str, k: int = 6,
                      component: Optional[str] = None, max_chars: int = 6000) -> str:
        """Formatted retrieved knowledge to inject into the system prompt."""
        hits = self.retrieve(query, k=k, component=component)
        blocks, used = [], 0
        for score, ch in hits:
            head = f"[{ch['component']} · {ch['path']}:{ch['start_line']}-{ch['end_line']}] (rel={score:.2f})"
            piece = f"{head}\n{ch['text']}"
            if used + len(piece) > max_chars:
                piece = piece[: max(0, max_chars - used)]
            blocks.append(piece)
            used += len(piece)
            if used >= max_chars:
                break
        return "\n\n---\n\n".join(blocks)

    def sources(self, query: str, k: int = 6) -> List[Dict]:
        return [{"path": ch["path"], "component": ch["component"],
                 "lines": f"{ch['start_line']}-{ch['end_line']}", "score": round(s, 3)}
                for s, ch in self.retrieve(query, k=k)]

    def stats(self) -> Dict:
        m = self.store.meta
        return {
            "ready": self.store.ready(),
            "stale": self.is_stale() if self.store.ready() else None,
            "built_at": m.get("built_at"),
            "chunk_count": m.get("chunk_count"),
            "file_count": m.get("file_count"),
            "embed_model": m.get("embed_model"),
            "components": m.get("components", {}),
            "index_dir": str(self.store.dir),
        }


if __name__ == "__main__":  # python -m ub.knowledge_engine.engine  → build the index
    KnowledgeEngine().build()
