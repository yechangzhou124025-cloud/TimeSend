from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class TimeSyncResult:
    success: bool
    return_code: int | None
    output: str


def sync_windows_time(timeout: float = 15.0) -> TimeSyncResult:
    if os.name != "nt":
        return TimeSyncResult(False, None, "系统时间同步仅支持 Windows")
    try:
        result = subprocess.run(
            ["w32tm", "/resync"],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        return TimeSyncResult(result.returncode == 0, result.returncode, output)
    except (OSError, subprocess.SubprocessError) as exc:
        return TimeSyncResult(False, None, str(exc))
