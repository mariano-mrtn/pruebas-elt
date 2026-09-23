"""Tests para tools/monitor_binance_stability.py (10.2)."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.monitor_binance_stability import classify


def _fake_response(status_code, json_body=None, text=""):
    def json_fn():
        if json_body is None:
            raise ValueError("no json")
        return json_body

    return SimpleNamespace(status_code=status_code, json=json_fn, text=text)


def test_classify_ok():
    r = _fake_response(200, json_body=[[1, 2, 3]])
    status, note = classify(r, 100)
    assert status == "OK"


def test_classify_throttled():
    for code in (429, 418):
        status, _ = classify(_fake_response(code), 100)
        assert status == "THROTTLED"


def test_classify_blocked():
    for code in (403, 451):
        status, _ = classify(_fake_response(code), 100)
        assert status == "BLOCKED"


def test_classify_server_error():
    status, _ = classify(_fake_response(503, text="upstream error"), 100)
    assert status == "HTTP_503"


def test_classify_bad_body():
    status, _ = classify(_fake_response(200, json_body=[]), 100)
    assert status == "BAD_BODY"
