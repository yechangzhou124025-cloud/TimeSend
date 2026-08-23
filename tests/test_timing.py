import threading
import time

from app.scheduler import format_duration
from app.windows_timer import precise_wait_until


def test_format_duration() -> None:
    assert format_duration(3723.9) == "01:02:03"


def test_precise_wait_reaches_deadline() -> None:
    deadline = time.perf_counter_ns() + 5_000_000
    assert precise_wait_until(deadline)
    assert time.perf_counter_ns() >= deadline


def test_precise_wait_can_be_cancelled() -> None:
    cancel = threading.Event()
    cancel.set()
    assert not precise_wait_until(time.perf_counter_ns() + 1_000_000_000, cancel)
