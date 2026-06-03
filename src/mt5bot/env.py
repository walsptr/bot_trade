import os
from pathlib import Path
from typing import Optional


def _set_env(k: str, v: str, *, override: bool) -> None:
    k = k.strip()
    if not k:
        return
    if not override and os.getenv(k) is not None:
        return
    os.environ[k] = v


def load_env_file(path: Path, *, override: bool) -> None:
    if not path.exists():
        return
    raw = path.read_text(encoding="utf-8")
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip("'").strip('"')
        if not v:
            continue
        _set_env(k, v, override=override)


def default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_env(project_root: Optional[Path] = None) -> None:
    project_root = project_root or default_project_root()
    base_env = project_root / ".env"
    load_env_file(base_env, override=False)
