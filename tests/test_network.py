import requests

from app.network import measure_network


def test_measure_network_uses_one_request(monkeypatch) -> None:
    calls = []

    def fake_head(url, timeout):
        calls.append((url, timeout))
        return object()

    monkeypatch.setattr(requests, "head", fake_head)
    result = measure_network("https://example.test", timeout=1.0)
    assert result.success
    assert result.rtt_ms is not None
    assert result.compensation_ms == result.rtt_ms / 2
    assert calls == [("https://example.test", 1.0)]


def test_measure_network_failure_returns_zero(monkeypatch) -> None:
    def fail(_url, timeout):
        raise requests.Timeout(f"timeout={timeout}")

    monkeypatch.setattr(requests, "head", fail)
    result = measure_network("https://example.test")
    assert not result.success
    assert result.rtt_ms is None
    assert result.compensation_ms == 0.0
