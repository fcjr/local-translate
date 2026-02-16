"""Shared utility for locating the Python interpreter used by worker subprocesses."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def find_python() -> str:
    """Find a Python executable for spawning worker subprocesses.

    Resolution order:
    1. LOCAL_TRANSLATE_PYTHON env var (set by the Rust host in main.rs)
    2. sys.executable if it points to a real Python binary
    3. Dev fallback: .venv/bin/python3 relative to the project root
    """
    # 1. Env var set explicitly by the Rust host
    env_python = os.environ.get("LOCAL_TRANSLATE_PYTHON")
    if env_python:
        p = Path(env_python)
        if p.is_file():
            return str(p)

    # 2. sys.executable (works in pytauri standalone builds)
    if sys.executable and Path(sys.executable).is_file():
        exe_name = Path(sys.executable).name.lower()
        if "python" in exe_name:
            return sys.executable

    # 3. Dev fallback: venv relative to the project root
    pkg_dir = Path(__file__).resolve().parent
    project_root = pkg_dir.parent.parent.parent
    venv_python = project_root / ".venv" / "bin" / "python3"
    if venv_python.is_file():
        return str(venv_python)

    raise FileNotFoundError(
        "Could not find a Python executable for worker subprocesses. "
        "Ensure LOCAL_TRANSLATE_PYTHON is set or a .venv exists."
    )
