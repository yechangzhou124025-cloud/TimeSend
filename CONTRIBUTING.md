# 参与贡献

感谢你愿意改进 TimeSend。提交 Pull Request 前，请先确认改动范围清晰，并避免提交个人配置、日志、构建产物或聊天内容。

## 本地开发

```bat
py -m venv .venv
.venv\Scripts\activate
py -m pip install -r requirements-dev.txt
```

提交前运行：

```bat
py -m pytest -q
py -m ruff check .
py -m compileall -q main.py app tests
```

涉及 `SendInput`、系统托盘、单实例或 PyInstaller 的改动，还应在 Windows 10/11 真机验证。自动化测试不能证明前台窗口按键注入行为正确。

## 提交约定

- 一个 Pull Request 尽量只解决一个问题；
- 行为变化应补充或更新测试；
- 用户可见变化应同步更新 `README.md`；
- 不要在 Issue、日志或截图中公开聊天消息及其他隐私信息。
