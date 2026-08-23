import json

from app.config_store import ConfigStore
from app.models import AppConfig


def test_config_round_trip(tmp_path) -> None:
    path = tmp_path / "config.json"
    store = ConfigStore(path)
    expected = AppConfig(target_time="09:01:02.003", network_mode="manual", network_compensation_ms=7.5)
    store.save(expected)
    loaded = store.load()
    assert loaded.warning is None
    assert loaded.config == expected


def test_broken_config_recovers_defaults(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{broken", encoding="utf-8")
    loaded = ConfigStore(path).load()
    assert loaded.config == AppConfig()
    assert loaded.warning
    assert path.with_suffix(".broken.json").exists()


def test_unknown_keys_are_ignored(tmp_path) -> None:
    path = tmp_path / "config.json"
    raw = AppConfig().to_dict() | {"future_key": True}
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert ConfigStore(path).load().config == AppConfig()
