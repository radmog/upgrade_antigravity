"""Cache textual privado para metadados HTTP."""

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict


@dataclass(frozen=True)
class CacheResult:
    text: str
    status: str


class TextCache:
    def __init__(self, directory: Path, ttl: int):
        self.directory = directory
        self.ttl = ttl

    def _paths(self, url: str):
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.directory / f"{key}.txt", self.directory / f"{key}.json"

    def _read(self, url: str):
        body, metadata = self._paths(url)
        if any(path.is_symlink() or not path.is_file() for path in (body, metadata)):
            return None
        try:
            info = json.loads(metadata.read_text(encoding="utf-8"))
            if info.get("url") != url or not isinstance(info.get("saved_at"), (int, float)):
                return None
            return body.read_text(encoding="utf-8"), float(info["saved_at"])
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def _write(self, url: str, text: str) -> None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.is_symlink():
            raise OSError(f"Diretório de cache inseguro: {self.directory}")
        self.directory.chmod(0o700)
        body, metadata = self._paths(url)
        suffix = f".tmp-{os.getpid()}-{time.time_ns()}"
        body_tmp = body.with_name(body.name + suffix)
        metadata_tmp = metadata.with_name(metadata.name + suffix)
        try:
            body_tmp.write_text(text, encoding="utf-8")
            metadata_tmp.write_text(
                json.dumps({"url": url, "saved_at": time.time()}, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            body_tmp.chmod(0o600)
            metadata_tmp.chmod(0o600)
            os.replace(body_tmp, body)
            os.replace(metadata_tmp, metadata)
        finally:
            for temporary in (body_tmp, metadata_tmp):
                if temporary.exists():
                    temporary.unlink()

    def fetch(self, url: str, loader: Callable[[str], str]) -> CacheResult:
        if self.ttl == 0:
            return CacheResult(loader(url), "disabled")
        cached = self._read(url)
        if cached and self.ttl > 0 and time.time() - cached[1] <= self.ttl:
            return CacheResult(cached[0], "hit")
        text = loader(url)
        if text:
            try:
                self._write(url, text)
            except OSError:
                pass
            return CacheResult(text, "miss")
        if cached:
            return CacheResult(cached[0], "stale")
        return CacheResult("", "miss")

    def clear(self) -> int:
        if not self.directory.exists():
            return 0
        if self.directory.is_symlink() or not self.directory.is_dir():
            raise ValueError(f"Diretório de cache inseguro: {self.directory}")
        removed = 0
        for candidate in self.directory.iterdir():
            if candidate.is_file() or candidate.is_symlink():
                candidate.unlink()
                removed += 1
        return removed

    def stats(self) -> Dict[str, int]:
        if not self.directory.is_dir() or self.directory.is_symlink():
            return {"files": 0, "bytes": 0}
        files = [item for item in self.directory.iterdir() if item.is_file() and not item.is_symlink()]
        return {"files": len(files), "bytes": sum(item.stat().st_size for item in files)}
