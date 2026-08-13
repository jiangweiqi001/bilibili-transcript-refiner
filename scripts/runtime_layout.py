from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path


def is_ascii_path(path: Path | str) -> bool:
    try:
        str(path).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _normalized_source(value: str) -> str:
    return os.path.normcase(os.path.abspath(value)).rstrip("\\/")


def user_key(local_app_data: str) -> str:
    source = _normalized_source(local_app_data).encode("utf-8")
    return hashlib.sha256(source).hexdigest()[:16]


def default_runtime_root(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    local_app_data = env.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is not defined")
    primary = Path(local_app_data) / "bilibili-transcript-refiner" / "runtime-v1"
    if is_ascii_path(primary):
        return primary
    public = env.get("PUBLIC")
    if not public:
        raise RuntimeError("Unicode profile requires an explicit ASCII --runtime-root")
    fallback = (
        Path(public)
        / "bilibili-transcript-refiner"
        / "users"
        / user_key(local_app_data)
        / "runtime-v1"
    )
    if not is_ascii_path(fallback):
        raise RuntimeError("Unicode profile requires an explicit ASCII --runtime-root")
    return fallback
