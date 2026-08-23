from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from typing import Any, Literal

NetworkMode = Literal["manual", "auto"]


@dataclass(frozen=True)
class AppConfig:
    target_time: str = "08:00:00.000"
    network_mode: NetworkMode = "auto"
    network_compensation_ms: float = 0.0
    extra_compensation_ms: float = 4.0
    max_advance_ms: float = 80.0
    auto_measure_lead_seconds: float = 2.0
    rtt_url: str = "https://oapi.dingtalk.com"

    def validated(self) -> AppConfig:
        parse_time(self.target_time)
        if self.network_mode not in ("manual", "auto"):
            raise ValueError("网络模式必须是 manual 或 auto")
        for label, value, upper in (
            ("网络补偿", self.network_compensation_ms, 60_000.0),
            ("额外补偿", self.extra_compensation_ms, 60_000.0),
            ("最大提前量", self.max_advance_ms, 60_000.0),
            ("自动测速提前时间", self.auto_measure_lead_seconds, 300.0),
        ):
            if not isinstance(value, (int, float)) or not 0 <= float(value) <= upper:
                raise ValueError(f"{label}超出允许范围")
        if not isinstance(self.rtt_url, str) or not self.rtt_url.startswith(("http://", "https://")):
            raise ValueError("测速地址无效")
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AppConfig:
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: raw[key] for key in allowed if key in raw}).validated()


@dataclass(frozen=True)
class AdvanceCalculation:
    network_ms: float
    extra_ms: float
    theoretical_ms: float
    final_ms: float
    capped: bool


def calculate_advance(network_ms: float, extra_ms: float, max_ms: float) -> AdvanceCalculation:
    network = max(0.0, float(network_ms))
    extra = max(0.0, float(extra_ms))
    maximum = max(0.0, float(max_ms))
    theoretical = network + extra
    final = min(theoretical, maximum)
    return AdvanceCalculation(network, extra, theoretical, final, theoretical > maximum)


def parse_time(value: str) -> time:
    try:
        parsed = datetime.strptime(value, "%H:%M:%S.%f").time()
    except (TypeError, ValueError) as exc:
        raise ValueError("时间格式必须为 HH:MM:SS.mmm") from exc
    return parsed


def format_time(value: time) -> str:
    return value.strftime("%H:%M:%S.%f")[:-3]


def target_datetime_today(value: str, now: datetime | None = None) -> datetime:
    reference = now or datetime.now()
    return datetime.combine(reference.date(), parse_time(value))


def trigger_datetime(target: datetime, advance_ms: float) -> datetime:
    return target - timedelta(milliseconds=max(0.0, advance_ms))
