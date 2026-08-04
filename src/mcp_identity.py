"""Dependency-light MCP identity helpers."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Iterable


def stdio_launch_identity_hash(command: str, args: Iterable[str]) -> str:
    """Return a non-secret identity for the executable name and exact argv."""

    executable = os.path.basename(str(command or "")).casefold()
    if executable in {"npx.cmd", "npx.exe"}:
        executable = "npx"
    payload = json.dumps(
        ["stdio", executable, [str(value) for value in (args or [])]],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
