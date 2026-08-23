from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app.config_store import ConfigStore
from app.gui import MainWindow
from app.logging_setup import setup_logging
from app.single_instance import SingleInstance
from app.windows_timer import TimerResolution


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("DingTalkAutoSend")
    app.setQuitOnLastWindowClosed(False)

    instance = SingleInstance()
    if not instance.acquire():
        QMessageBox.information(None, "程序已在运行", "钉钉定时发送助手已经在运行，请查看系统托盘。")
        return 0

    logger, log_file = setup_logging()
    logger.info("程序启动 | platform=%s", sys.platform)
    timer_resolution = TimerResolution(1)
    timer_ok = timer_resolution.begin()
    logger.info("timeBeginPeriod(1) | success=%s", timer_ok)

    window = MainWindow(ConfigStore(), logger, log_file)
    window.show()
    if os.name != "nt":
        QMessageBox.warning(
            window, "非 Windows 环境", "当前系统只能预览界面，无法实际发送 Enter 或调用 w32tm。"
        )
    QTimer.singleShot(500, window.sync_time_async)

    try:
        return app.exec()
    finally:
        window.scheduler.stop()
        timer_resolution.end()
        instance.release()
        logger.info("程序退出")


if __name__ == "__main__":
    raise SystemExit(main())
