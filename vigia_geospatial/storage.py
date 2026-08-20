import hashlib
import os
from pathlib import Path, PurePosixPath
from typing import Protocol


class ObjectStorage(Protocol):
    def exists(self, key: str) -> bool: ...
    def put(self, key: str, content: bytes) -> tuple[str, str]: ...
    def uri(self, key: str) -> str: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        pure = PurePosixPath(key)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise ValueError("Clave de almacenamiento no válida.")
        target = self.root.joinpath(*pure.parts).resolve()
        if self.root not in target.parents:
            raise ValueError("La clave sale del almacenamiento permitido.")
        return target

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def put(self, key: str, content: bytes) -> tuple[str, str]:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(content).hexdigest()
        temporary = target.with_suffix(target.suffix + ".part")
        temporary.write_bytes(content)
        os.replace(temporary, target)
        return self.uri(key), digest

    def uri(self, key: str) -> str:
        return self._path(key).as_uri()
