from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter_ns

import requests


@dataclass(frozen=True)
class NetworkMeasurement:
    success: bool
    rtt_ms: float | None
    compensation_ms: float
    error: str | None = None


def measure_network(url: str, timeout: float = 1.0) -> NetworkMeasurement:
    started = perf_counter_ns()
    try:
        # Any HTTP response proves the round trip completed; a 4xx response is
        # still a valid latency sample for this endpoint.
        requests.head(url, timeout=timeout)
    except requests.RequestException as exc:
        return NetworkMeasurement(False, None, 0.0, str(exc))
    elapsed_ms = (perf_counter_ns() - started) / 1_000_000
    return NetworkMeasurement(True, elapsed_ms, elapsed_ms / 2.0)
