from __future__ import annotations

from pathlib import Path
from typing import Dict


def load_env_file(path: str) -> Dict[str, str]:
    """Minimal .env loader: KEY=VALUE lines, ignores comments and blanks."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Secrets file not found: {path}")

    out: Dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out
