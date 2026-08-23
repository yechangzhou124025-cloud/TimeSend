from __future__ import annotations

import ctypes
import os
import threading
import time
from datetime import datetime
from typing import Self


class TimerResolution:
    def __init__(self, milliseconds: int = 1) -> None:
        self.milliseconds = milliseconds
        self.active = False

    def begin(self) -> bool:
        if os.name != "nt":
            return False
        result = ctypes.windll.winmm.timeBeginPeriod(self.milliseconds)
        self.active = result == 0
        return self.active

    def end(self) -> None:
        if self.active and os.name == "nt":
            ctypes.windll.winmm.timeEndPeriod(self.milliseconds)
            self.active = False

    def __enter__(self) -> Self:
        self.begin()
        return self

    def __exit__(self, *_args: object) -> None:
        self.end()


def wall_datetime_to_perf_ns(target: datetime) -> int:
    delta_ns = int((target - datetime.now()).total_seconds() * 1_000_000_000)
    return time.perf_counter_ns() + delta_ns


def precise_wait_until(
    deadline_ns: int,
    cancel_event: threading.Event | None = None,
    spin_threshold_ms: float = 50.0,
) -> bool:
    """Wait until a monotonic deadline; return False when cancelled."""
    cancelled = cancel_event or threading.Event()
    spin_ns = int(spin_threshold_ms * 1_000_000)
    while True:
        if cancelled.is_set():
            return False
        remaining = deadline_ns - time.perf_counter_ns()
        if remaining <= 0:
            return True
        if remaining > 1_000_000_000:
            cancelled.wait(min((remaining - 500_000_000) / 1e9, 0.5))
        elif remaining > 100_000_000:
            cancelled.wait(min((remaining - 50_000_000) / 1e9, 0.05))
        elif remaining > spin_ns:
            time.sleep(min(0.001, max(0.0, (remaining - spin_ns) / 1e9)))
        else:
            # The final short spin avoids the scheduler overshoot of a sleep call.
            pass
