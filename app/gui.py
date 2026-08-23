from __future__ import annotations

import threading
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QTime, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .config_store import ConfigStore
from .models import AppConfig, calculate_advance, parse_time, target_datetime_today, trigger_datetime
from .network import NetworkMeasurement, measure_network
from .scheduler import OneShotScheduler
from .time_sync import TimeSyncResult, sync_windows_time


class MainWindow(QMainWindow):
    scheduler_status = Signal(str)
    scheduler_network = Signal(object)
    scheduler_finished = Signal(object, str)
    manual_network_done = Signal(object, bool)
    time_sync_done = Signal(object)

    def __init__(self, store: ConfigStore, logger, log_file: Path) -> None:
        super().__init__()
        self.store = store
        self.logger = logger
        self.log_file = log_file
        loaded = store.load()
        self.config = loaded.config
        self._quitting = False

        self.scheduler_status.connect(self._set_status)
        self.scheduler_network.connect(self._apply_auto_network_result)
        self.scheduler_finished.connect(self._on_task_finished)
        self.manual_network_done.connect(self._on_manual_network_done)
        self.time_sync_done.connect(self._on_time_sync_done)
        self.scheduler = OneShotScheduler(
            logger,
            on_status=self.scheduler_status.emit,
            on_network=self.scheduler_network.emit,
            on_finished=self.scheduler_finished.emit,
        )

        self.setWindowTitle("钉钉定时发送助手")
        self.setMinimumWidth(600)
        self._build_ui()
        self._build_tray()
        self._load_widgets(self.config)
        self._connect_changes()
        self._update_mode()
        self._update_preview()
        if loaded.warning:
            self.logger.warning(loaded.warning)
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, "配置已恢复", loaded.warning))

    def _build_ui(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)

        send_group = QGroupBox("本次发送")
        send_form = QFormLayout(send_group)
        self.target_time = QTimeEdit()
        self.target_time.setDisplayFormat("HH:mm:ss.zzz")
        self.target_time.setTime(QTime(8, 0, 0, 0))
        send_form.addRow("目标时间", self.target_time)
        self.arm_check = QCheckBox("启用本次发送")
        send_form.addRow("", self.arm_check)
        layout.addWidget(send_group)

        compensation_group = QGroupBox("时间补偿")
        compensation_form = QFormLayout(compensation_group)
        self.network_mode = QComboBox()
        self.network_mode.addItem("自动测速", "auto")
        self.network_mode.addItem("手动设置", "manual")
        compensation_form.addRow("网络方式", self.network_mode)
        self.network_ms = self._milliseconds_box(0.0)
        compensation_form.addRow("网络补偿", self.network_ms)
        self.measure_button = QPushButton("立即测速")
        compensation_form.addRow("", self.measure_button)
        self.extra_ms = self._milliseconds_box(4.0)
        compensation_form.addRow("额外补偿", self.extra_ms)
        self.max_ms = self._milliseconds_box(80.0)
        compensation_form.addRow("最大提前量", self.max_ms)
        self.calibration_hint = QLabel("发送偏晚就增大额外补偿；发送偏早就减小额外补偿。")
        self.calibration_hint.setWordWrap(True)
        compensation_form.addRow("", self.calibration_hint)
        layout.addWidget(compensation_group)

        result_group = QGroupBox("当前结果")
        result_form = QFormLayout(result_group)
        self.final_advance_label = QLabel()
        self.trigger_label = QLabel()
        self.warning_label = QLabel()
        self.warning_label.setStyleSheet("color: #b3261e; font-weight: 600;")
        self.warning_label.setWordWrap(True)
        result_form.addRow("最终提前", self.final_advance_label)
        result_form.addRow("预计按下 Enter", self.trigger_label)
        result_form.addRow("", self.warning_label)
        layout.addWidget(result_group)

        test_group = QGroupBox("测试与日志")
        test_layout = QVBoxLayout(test_group)
        row1 = QHBoxLayout()
        self.five_second_test = QPushButton("5秒后测试 Enter")
        self.sync_button = QPushButton("同步系统时间")
        self.open_log_button = QPushButton("查看日志")
        row1.addWidget(self.five_second_test)
        row1.addWidget(self.sync_button)
        row1.addWidget(self.open_log_button)
        test_layout.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("精度测试时间"))
        self.precision_time = QTimeEdit()
        self.precision_time.setDisplayFormat("HH:mm:ss.zzz")
        self.precision_time.setTime(QTime.currentTime().addSecs(30))
        self.precision_button = QPushButton("开始精度测试")
        row2.addWidget(self.precision_time)
        row2.addWidget(self.precision_button)
        test_layout.addLayout(row2)
        self.test_warning = QLabel("注意：所有测试都会向触发时刻的当前前台窗口真实发送一次 Enter。")
        self.test_warning.setStyleSheet("color: #b3261e;")
        self.test_warning.setWordWrap(True)
        test_layout.addWidget(self.test_warning)
        layout.addWidget(test_group)

        self.front_warning = QLabel(
            "程序不会查找或激活钉钉。离开电脑前，请确保正确的群聊输入框一直位于前台，并避免其他窗口或弹窗抢占焦点。"
        )
        self.front_warning.setWordWrap(True)
        self.front_warning.setStyleSheet("padding: 8px; background: #fff4e5; color: #663c00;")
        layout.addWidget(self.front_warning)
        self.setCentralWidget(root)
        self.statusBar().showMessage("尚未启用本次发送")

    @staticmethod
    def _milliseconds_box(default: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(0.0, 60_000.0)
        box.setDecimals(3)
        box.setValue(default)
        box.setSuffix(" ms")
        box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        box.setKeyboardTracking(False)
        return box

    def _build_tray(self) -> None:
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(QIcon(icon), self)
        menu = self.tray.contextMenu() or None
        if menu is None:
            from PySide6.QtWidgets import QMenu

            menu = QMenu()
        open_action = QAction("打开主界面", self)
        open_action.triggered.connect(self._restore_window)
        self.tray_arm_action = QAction("启用本次发送", self)
        self.tray_arm_action.setCheckable(True)
        self.tray_arm_action.triggered.connect(self.arm_check.setChecked)
        log_action = QAction("查看日志", self)
        log_action.triggered.connect(self._open_log)
        quit_action = QAction("退出程序", self)
        quit_action.triggered.connect(self.quit_application)
        menu.addAction(open_action)
        menu.addAction(self.tray_arm_action)
        menu.addAction(log_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: (
                self._restore_window() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None
            )
        )
        self.tray.show()

    def _connect_changes(self) -> None:
        self.target_time.timeChanged.connect(self._settings_changed)
        self.network_mode.currentIndexChanged.connect(self._settings_changed)
        self.network_mode.currentIndexChanged.connect(self._update_mode)
        self.network_ms.valueChanged.connect(self._settings_changed)
        self.extra_ms.valueChanged.connect(self._settings_changed)
        self.max_ms.valueChanged.connect(self._settings_changed)
        self.arm_check.toggled.connect(self._toggle_arm)
        self.arm_check.toggled.connect(self.tray_arm_action.setChecked)
        self.measure_button.clicked.connect(self._measure_now)
        self.five_second_test.clicked.connect(self._start_five_second_test)
        self.precision_button.clicked.connect(self._start_precision_test)
        self.sync_button.clicked.connect(self.sync_time_async)
        self.open_log_button.clicked.connect(self._open_log)

    def _load_widgets(self, config: AppConfig) -> None:
        parsed = parse_time(config.target_time)
        self.target_time.setTime(QTime(parsed.hour, parsed.minute, parsed.second, parsed.microsecond // 1000))
        index = self.network_mode.findData(config.network_mode)
        self.network_mode.setCurrentIndex(max(0, index))
        self.network_ms.setValue(config.network_compensation_ms)
        self.extra_ms.setValue(config.extra_compensation_ms)
        self.max_ms.setValue(config.max_advance_ms)

    def _config_from_widgets(self) -> AppConfig:
        value = self.target_time.time()
        target = f"{value.hour():02d}:{value.minute():02d}:{value.second():02d}.{value.msec():03d}"
        return AppConfig(
            target_time=target,
            network_mode=self.network_mode.currentData(),
            network_compensation_ms=self.network_ms.value(),
            extra_compensation_ms=self.extra_ms.value(),
            max_advance_ms=self.max_ms.value(),
            auto_measure_lead_seconds=2.0,
            rtt_url=self.config.rtt_url,
        ).validated()

    def _settings_changed(self, *_args) -> None:
        try:
            self.config = self._config_from_widgets()
            self.store.save(self.config)
            self._update_preview()
            if self.arm_check.isChecked():
                self.scheduler.arm(self.config)
                self._set_status("设置已更新，本次任务已重新安排")
        except (OSError, ValueError) as exc:
            self._set_status(f"设置无效：{exc}")

    def _update_mode(self, *_args) -> None:
        automatic = self.network_mode.currentData() == "auto"
        self.network_ms.setReadOnly(automatic)
        self.network_ms.setToolTip("自动测速后由程序填写" if automatic else "请输入网络补偿")

    def _update_preview(self) -> None:
        calculation = calculate_advance(self.network_ms.value(), self.extra_ms.value(), self.max_ms.value())
        target = target_datetime_today(self._config_from_widgets().target_time)
        trigger = trigger_datetime(target, calculation.final_ms)
        self.final_advance_label.setText(f"{calculation.final_ms:.3f} ms")
        self.trigger_label.setText(trigger.strftime("%H:%M:%S.%f")[:-3])
        if calculation.capped:
            self.warning_label.setText(
                f"计算结果 {calculation.theoretical_ms:.3f} ms 超过安全上限，"
                f"本次按 {calculation.final_ms:.3f} ms 执行。"
            )
        else:
            self.warning_label.clear()

    def _toggle_arm(self, enabled: bool) -> None:
        self.sync_button.setEnabled(not enabled)
        if enabled:
            try:
                self.config = self._config_from_widgets()
                self.store.save(self.config)
                self.scheduler.arm(self.config)
                self._set_status(f"本次发送已启用，目标 {self.config.target_time}")
            except (OSError, RuntimeError, ValueError) as exc:
                self.arm_check.blockSignals(True)
                self.arm_check.setChecked(False)
                self.arm_check.blockSignals(False)
                self.tray_arm_action.setChecked(False)
                QMessageBox.warning(self, "无法启用", str(exc))
        else:
            self.scheduler.cancel()

    def _measure_now(self) -> None:
        if not self.measure_button.isEnabled():
            return
        self.measure_button.setEnabled(False)
        self._set_status("正在测试网络")
        apply_value = self.network_mode.currentData() == "auto"
        url = self.config.rtt_url

        def work() -> None:
            self.manual_network_done.emit(measure_network(url, timeout=1.0), apply_value)

        threading.Thread(target=work, name="ManualNetworkTest", daemon=True).start()

    def _on_manual_network_done(self, result: NetworkMeasurement, apply_value: bool) -> None:
        self.measure_button.setEnabled(True)
        if result.success:
            if apply_value:
                self.network_ms.setValue(result.compensation_ms)
                message = f"测速完成，网络补偿已更新为 {result.compensation_ms:.3f} ms"
            else:
                message = f"测速完成，参考网络补偿为 {result.compensation_ms:.3f} ms（未修改手动值）"
            self.logger.info(
                "立即测速成功 | rtt_ms=%.3f compensation_ms=%.3f", result.rtt_ms, result.compensation_ms
            )
        else:
            message = f"测速失败：{result.error}"
            self.logger.warning("立即测速失败 | error=%s", result.error)
        self._set_status(message)

    def _apply_auto_network_result(self, result: NetworkMeasurement) -> None:
        if result.success:
            self.network_ms.blockSignals(True)
            self.network_ms.setValue(result.compensation_ms)
            self.network_ms.blockSignals(False)
            self.config = self._config_from_widgets()
            try:
                self.store.save(self.config)
            except OSError as exc:
                self.logger.warning("自动测速结果保存失败 | error=%s", exc)
            self._update_preview()

    def _start_five_second_test(self) -> None:
        if (
            QMessageBox.warning(
                self,
                "确认真实按键测试",
                "5秒后会向当时的前台窗口真实发送一次 Enter。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.arm_check.setChecked(False)
        self.scheduler.schedule_simple_test(datetime.now() + timedelta(seconds=5), "5秒Enter测试")

    def _start_precision_test(self) -> None:
        qtime = self.precision_time.time()
        target = datetime.now().replace(
            hour=qtime.hour(),
            minute=qtime.minute(),
            second=qtime.second(),
            microsecond=qtime.msec() * 1000,
        )
        if target <= datetime.now():
            QMessageBox.warning(self, "测试时间无效", "精度测试时间必须晚于当前时间。")
            return
        if (
            QMessageBox.warning(
                self,
                "确认精度测试",
                f"将在 {target.strftime('%H:%M:%S.%f')[:-3]} 向前台窗口真实发送 Enter。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.arm_check.setChecked(False)
        self.scheduler.schedule_simple_test(target, "定时精度测试")

    def sync_time_async(self) -> None:
        self.sync_button.setEnabled(False)
        self._set_status("正在同步系统时间")
        threading.Thread(
            target=lambda: self.time_sync_done.emit(sync_windows_time()),
            name="WindowsTimeSync",
            daemon=True,
        ).start()

    def _on_time_sync_done(self, result: TimeSyncResult) -> None:
        self.sync_button.setEnabled(not self.arm_check.isChecked())
        level = self.logger.info if result.success else self.logger.warning
        level(
            "系统时间同步 | success=%s return_code=%s output=%s",
            result.success,
            result.return_code,
            result.output,
        )
        self._set_status("系统时间同步成功" if result.success else f"系统时间同步失败：{result.output}")
        if self.arm_check.isChecked():
            try:
                self.scheduler.arm(self._config_from_widgets())
                self._set_status("系统时间同步完成，本次任务已按新系统时间重新安排")
            except (RuntimeError, ValueError) as exc:
                self.arm_check.setChecked(False)
                self._set_status(f"时间同步后无法重新安排任务：{exc}")

    def _on_task_finished(self, _result, message: str) -> None:
        self.arm_check.blockSignals(True)
        self.arm_check.setChecked(False)
        self.arm_check.blockSignals(False)
        self.tray_arm_action.setChecked(False)
        self.sync_button.setEnabled(True)
        self._set_status(message)

    def _set_status(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def _open_log(self) -> None:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.touch(exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_file)))

    def _restore_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting:
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "钉钉定时发送助手", "程序仍在托盘运行。", QSystemTrayIcon.MessageIcon.Information, 2500
        )

    def quit_application(self) -> None:
        self._quitting = True
        self.scheduler.stop()
        self.tray.hide()
        QApplication.instance().quit()
