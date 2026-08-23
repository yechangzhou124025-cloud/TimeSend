from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .input_sender import SendResult, send_enter
from .models import AdvanceCalculation, AppConfig, calculate_advance, target_datetime_today, trigger_datetime
from .network import NetworkMeasurement, measure_network
from .windows_timer import precise_wait_until, wall_datetime_to_perf_ns

StatusCallback = Callable[[str], None]
NetworkCallback = Callable[[NetworkMeasurement], None]
FinishedCallback = Callable[[SendResult | None, str], None]


@dataclass(frozen=True)
class SchedulePreview:
    target: datetime
    trigger: datetime
    calculation: AdvanceCalculation


class OneShotScheduler:
    def __init__(
        self,
        logger: logging.Logger,
        on_status: StatusCallback | None = None,
        on_network: NetworkCallback | None = None,
        on_finished: FinishedCallback | None = None,
    ) -> None:
        self.logger = logger
        self.on_status = on_status or (lambda _message: None)
        self.on_network = on_network or (lambda _result: None)
        self.on_finished = on_finished or (lambda _result, _message: None)
        self._lock = threading.Lock()
        self._cancel: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._stopping = False

    @property
    def active(self) -> bool:
        with self._lock:
            return bool(
                self._thread and self._thread.is_alive() and self._cancel and not self._cancel.is_set()
            )

    @staticmethod
    def preview(
        config: AppConfig, network_ms: float | None = None, now: datetime | None = None
    ) -> SchedulePreview:
        checked = config.validated()
        target = target_datetime_today(checked.target_time, now)
        network = checked.network_compensation_ms if network_ms is None else network_ms
        calculation = calculate_advance(network, checked.extra_compensation_ms, checked.max_advance_ms)
        return SchedulePreview(target, trigger_datetime(target, calculation.final_ms), calculation)

    def arm(self, config: AppConfig) -> None:
        checked = config.validated()
        preview = self.preview(checked)
        if preview.target <= datetime.now():
            raise ValueError("本次目标时间已经过去，请设置一个稍后的时间")
        self.cancel("任务已被新设置替换", notify=False)
        cancel = threading.Event()
        thread = threading.Thread(
            target=self._run_scheduled,
            args=(checked, cancel),
            name="OneShotScheduler",
            daemon=True,
        )
        with self._lock:
            if self._stopping:
                raise RuntimeError("调度器正在退出")
            self._cancel = cancel
            self._thread = thread
        self.logger.info(
            "任务启用 | target=%s mode=%s network_ms=%.3f extra_ms=%.3f max_ms=%.3f",
            preview.target.isoformat(timespec="milliseconds"),
            checked.network_mode,
            checked.network_compensation_ms,
            checked.extra_compensation_ms,
            checked.max_advance_ms,
        )
        thread.start()

    def schedule_simple_test(self, target: datetime, label: str) -> None:
        if target <= datetime.now():
            raise ValueError("测试时间必须晚于当前时间")
        self.cancel("任务已被测试替换", notify=False)
        cancel = threading.Event()
        thread = threading.Thread(
            target=self._run_simple_test,
            args=(target, label, cancel),
            name="EnterTestScheduler",
            daemon=True,
        )
        with self._lock:
            if self._stopping:
                raise RuntimeError("调度器正在退出")
            self._cancel = cancel
            self._thread = thread
        self.logger.info("%s 已安排 | planned=%s", label, target.isoformat(timespec="milliseconds"))
        thread.start()

    def cancel(self, reason: str = "用户取消了本次发送", notify: bool = True) -> None:
        with self._lock:
            cancel = self._cancel
        if cancel and not cancel.is_set():
            cancel.set()
            self.logger.info("任务取消 | reason=%s", reason)
            if notify:
                self.on_status(reason)

    def stop(self) -> None:
        with self._lock:
            self._stopping = True
            cancel = self._cancel
            thread = self._thread
        if cancel:
            cancel.set()
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    def _run_scheduled(self, config: AppConfig, cancel: threading.Event) -> None:
        try:
            target = target_datetime_today(config.target_time)
            network_ms = config.network_compensation_ms
            if config.network_mode == "auto":
                measure_at = target - timedelta(seconds=config.auto_measure_lead_seconds)
                if not self._coarse_wait(measure_at, target, cancel, "等待自动测速"):
                    return
                self.on_status("正在测试网络")
                measurement = measure_network(config.rtt_url, timeout=1.0)
                self.on_network(measurement)
                if measurement.success:
                    network_ms = measurement.compensation_ms
                    self.logger.info(
                        "自动测速成功 | rtt_ms=%.3f network_compensation_ms=%.3f",
                        measurement.rtt_ms,
                        measurement.compensation_ms,
                    )
                else:
                    network_ms = 0.0
                    self.logger.warning("自动测速失败，本次网络补偿为0ms | error=%s", measurement.error)

            calculation = calculate_advance(network_ms, config.extra_compensation_ms, config.max_advance_ms)
            planned = trigger_datetime(target, calculation.final_ms)
            if calculation.capped:
                self.logger.warning(
                    "安全上限生效 | theoretical_ms=%.3f final_ms=%.3f",
                    calculation.theoretical_ms,
                    calculation.final_ms,
                )
                self.on_status(f"提前量超过安全上限，本次按 {calculation.final_ms:.1f} ms 执行")
            self.logger.info(
                "发送计划 | target=%s planned_enter=%s network_ms=%.3f extra_ms=%.3f "
                "theoretical_ms=%.3f final_ms=%.3f",
                target.isoformat(timespec="milliseconds"),
                planned.isoformat(timespec="milliseconds"),
                calculation.network_ms,
                calculation.extra_ms,
                calculation.theoretical_ms,
                calculation.final_ms,
            )
            if not self._final_wait(planned, target, cancel):
                return
            self._send_and_report(planned, target, calculation, "正式发送")
        except Exception:
            self.logger.exception("调度任务异常")
            self.on_finished(None, "任务异常，已取消发送；请查看日志")
        finally:
            self._clear_current(cancel)

    def _run_simple_test(self, target: datetime, label: str, cancel: threading.Event) -> None:
        try:
            if not self._final_wait(target, target, cancel):
                return
            calculation = calculate_advance(0.0, 0.0, 0.0)
            self._send_and_report(target, target, calculation, label)
        except Exception:
            self.logger.exception("%s 异常", label)
            self.on_finished(None, f"{label}异常；请查看日志")
        finally:
            self._clear_current(cancel)

    def _coarse_wait(self, until: datetime, target: datetime, cancel: threading.Event, prefix: str) -> bool:
        while datetime.now() < until:
            if cancel.wait(0.25):
                return False
            remaining = max(0.0, (target - datetime.now()).total_seconds())
            self.on_status(f"{prefix}，距离目标 {format_duration(remaining)}")
        return not cancel.is_set()

    def _final_wait(self, planned: datetime, target: datetime, cancel: threading.Event) -> bool:
        if cancel.is_set():
            return False
        self.on_status(f"正在等待触发，计划 {planned.strftime('%H:%M:%S.%f')[:-3]}")
        deadline_ns = wall_datetime_to_perf_ns(planned)
        ok = precise_wait_until(deadline_ns, cancel)
        if not ok:
            return False
        # Keep target in the signature so future logging remains explicit.
        _ = target
        return True

    def _send_and_report(
        self,
        planned: datetime,
        target: datetime,
        calculation: AdvanceCalculation,
        label: str,
    ) -> None:
        result = send_enter(planned)
        plan_error_ms = (result.called_at - planned).total_seconds() * 1000
        target_offset_ms = (result.called_at - target).total_seconds() * 1000
        self.logger.info(
            "%s结果 | target=%s planned_enter=%s actual_enter=%s plan_error_ms=%+.3f "
            "target_offset_ms=%+.3f sent_events=%d success=%s error_code=%s error=%s",
            label,
            target.isoformat(timespec="milliseconds"),
            planned.isoformat(timespec="milliseconds"),
            result.called_at.isoformat(timespec="milliseconds"),
            plan_error_ms,
            target_offset_ms,
            result.sent_events,
            result.success,
            result.error_code,
            result.error,
        )
        if result.success:
            message = f"{label}完成，定时误差 {plan_error_ms:+.3f} ms"
        else:
            message = f"{label}失败：{result.error or 'SendInput失败'}"
        self.on_status(message)
        self.on_finished(result, message)

    def _clear_current(self, cancel: threading.Event) -> None:
        with self._lock:
            if self._cancel is cancel:
                self._cancel = None
                self._thread = None


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
