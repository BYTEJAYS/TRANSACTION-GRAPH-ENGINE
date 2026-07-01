"""
EvidenceStore — the off-chain file layer.

Per the BELS core principle, raw files are NEVER placed on the blockchain. They are
written to a content-addressed directory; only the SHA-256, size and metadata digest
are anchored. The layout is IPFS-friendly (content-addressed by hash) so this store can
later be swapped for an IPFS / S3 object backend behind the same interface.

    evidence_storage/<evidence_id>/<filename>      ← the artifact
    evidence_storage/<evidence_id>/manifest.json   ← off-chain metadata sidecar
"""
from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional

from .. import config
from ..models import EvidenceType
from ..security import sha256_hex, sha256_of_obj, utc_now_iso

# Extension → logical evidence type, used to auto-classify uploads.
_EXT_TYPE = {
    ".pdf": EvidenceType.PDF,
    ".png": EvidenceType.SCREENSHOT, ".jpg": EvidenceType.IMAGE, ".jpeg": EvidenceType.IMAGE,
    ".gif": EvidenceType.IMAGE, ".bmp": EvidenceType.IMAGE, ".webp": EvidenceType.IMAGE,
    ".mp3": EvidenceType.AUDIO, ".wav": EvidenceType.AUDIO, ".m4a": EvidenceType.AUDIO,
    ".mp4": EvidenceType.VIDEO, ".mov": EvidenceType.VIDEO, ".mkv": EvidenceType.VIDEO,
    ".log": EvidenceType.LOG, ".txt": EvidenceType.LOG,
    ".csv": EvidenceType.CSV, ".json": EvidenceType.JSON,
}


def classify(filename: str) -> EvidenceType:
    return _EXT_TYPE.get(Path(filename).suffix.lower(), EvidenceType.OTHER)


@dataclass
class StoredFile:
    evidence_id: str
    filename: str
    path: str
    size_bytes: int
    sha256: str
    mime_type: str
    metadata_hash: str
    stored_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EvidenceStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else config.EVIDENCE_STORAGE_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, evidence_id: str) -> Path:
        d = self.root / evidence_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self, evidence_id: str, filename: str, data: bytes,
             metadata: Optional[Dict[str, Any]] = None) -> StoredFile:
        """Persist a file + sidecar manifest. Returns its content-addressed descriptor."""
        safe_name = Path(filename).name or "artifact.bin"
        target = self._dir(evidence_id) / safe_name
        target.write_bytes(data)

        digest = sha256_hex(data)
        mime = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
        meta = {
            "evidence_id": evidence_id,
            "original_filename": safe_name,
            "size_bytes": len(data),
            "sha256": digest,
            "mime_type": mime,
            "evidence_type": classify(safe_name).value,
            "stored_at": utc_now_iso(),
            "user_metadata": metadata or {},
        }
        meta_hash = sha256_of_obj(meta)
        (self._dir(evidence_id) / "manifest.json").write_text(
            json.dumps({**meta, "metadata_hash": meta_hash}, indent=2), encoding="utf-8"
        )
        return StoredFile(
            evidence_id=evidence_id, filename=safe_name, path=str(target),
            size_bytes=len(data), sha256=digest, mime_type=mime,
            metadata_hash=meta_hash, stored_at=meta["stored_at"],
        )

    def read(self, evidence_id: str) -> Optional[bytes]:
        manifest = self.manifest(evidence_id)
        if not manifest:
            return None
        path = self._dir(evidence_id) / manifest["original_filename"]
        return path.read_bytes() if path.exists() else None

    def file_path(self, evidence_id: str) -> Optional[Path]:
        manifest = self.manifest(evidence_id)
        if not manifest:
            return None
        path = self._dir(evidence_id) / manifest["original_filename"]
        return path if path.exists() else None

    def manifest(self, evidence_id: str) -> Optional[Dict[str, Any]]:
        mpath = self.root / evidence_id / "manifest.json"
        if not mpath.exists():
            return None
        return json.loads(mpath.read_text(encoding="utf-8"))

    def current_hash(self, evidence_id: str) -> Optional[str]:
        """Recompute the SHA-256 of the file *as it sits on disk now* (for tamper checks)."""
        data = self.read(evidence_id)
        return sha256_hex(data) if data is not None else None


evidence_store = EvidenceStore()
