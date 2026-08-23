from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .models import AppConfig
from .paths import config_path


@dataclass(frozen=True)
class LoadResult:
    config: AppConfig
    warning: str | None = None


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_path()

    def load(self) -> LoadResult:
        if not self.path.exists():
            return LoadResult(AppConfig())
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise TypeError("配置根节点不是对象")
            return LoadResult(AppConfig.from_dict(raw))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            backup = self.path.with_suffix(".broken.json")
            try:
                os.replace(self.path, backup)
                detail = f"损坏配置已移至 {backup}"
            except OSError:
                detail = "无法备份损坏配置"
            return LoadResult(AppConfig(), f"配置无效，已恢复默认值：{exc}；{detail}")

    def save(self, config: AppConfig) -> None:
        checked = config.validated()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(checked.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
