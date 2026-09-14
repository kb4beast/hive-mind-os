"""Small dependency-free durable stores for learning boundary receipts.

Records are canonical JSON objects.  The store uses replace-on-write with an
atomic temporary file, so a process restart cannot expose a partially written
record.  Callers still own encryption and access control; this module never
stores secrets.
"""
from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar
from .brain_kernel.canonical import canonical_bytes

T = TypeVar("T")

class ContractStore(Generic[T]):
    def __init__(self, path: str | os.PathLike[str], decode: Callable[[dict[str, Any]], T]):
        self.path = Path(path)
        self.decode = decode
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if type(raw) is not dict or type(raw.get("records", {})) is not dict:
                raise ValueError("invalid contract store")
            self._records = raw["records"]

    def _flush(self) -> None:
        payload = canonical_bytes({"version": 1, "records": self._records})
        fd, name = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name): os.unlink(name)

    def put(self, key: str, value: T) -> T:
        if type(key) is not str or not key: raise ValueError("store key is required")
        from .brain_kernel.canonical import canonical_document
        self._records[key] = canonical_document(value)
        self._flush(); return value

    def get(self, key: str) -> T | None:
        value = self._records.get(key)
        return None if value is None else self.decode(dict(value))

    def values(self) -> tuple[T, ...]:
        return tuple(self.decode(dict(v)) for v in self._records.values())

    def delete(self, key: str) -> None:
        self._records.pop(key, None); self._flush()
