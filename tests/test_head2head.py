"""head2head log + report logic, offline (no API key, no network)."""

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "head2head", Path(__file__).parents[1] / "scripts" / "head2head.py")
h2h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h2h)


def test_append_and_rows_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(h2h, "OUT", tmp_path)
    h2h._append("results.vtu.ac.in", "submitted", http=201, goal="look up results")
    h2h._append("results.vtu.ac.in", "status_change", status="pending")
    rows = h2h._rows(tmp_path / "results-vtu-ac-in.jsonl")
    assert [r["event"] for r in rows] == ["submitted", "status_change"]
    assert rows[1]["status"] == "pending"
    assert datetime.fromisoformat(rows[0]["t"]).tzinfo is not None


def test_receipt_mirrors_log_in_scorecard_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(h2h, "OUT", tmp_path)
    h2h._append("a.test", "submitted", http=201, goal="find things")
    h2h._append("a.test", "status_change", status="pending")
    h2h._append("a.test", "status_change", status="success", action_id="act_1")
    receipt = json.loads((tmp_path / "a-test__anakin.json").read_text(encoding="utf-8"))
    assert receipt["system"] == "anakin-build-request"
    assert receipt["goal"] == "find things"
    assert [e["status"] for e in receipt["events"]] == ["submitted", "pending", "shipped"]


def test_report_computes_elapsed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(h2h, "OUT", tmp_path)
    path = tmp_path / "a-test.jsonl"
    t0 = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 26, 10, 45, tzinfo=timezone.utc)
    path.write_text(
        json.dumps({"t": t0.isoformat(timespec="seconds"), "event": "submitted"}) + "\n"
        + json.dumps({"t": t1.isoformat(timespec="seconds"), "event": "status_change", "status": "failed"}) + "\n",
        encoding="utf-8")
    h2h.report()
    out = capsys.readouterr().out
    assert "a-test" in out and "failed after 45.0 min" in out


def test_missing_key_exits(monkeypatch):
    monkeypatch.delenv("ANAKIN_API_KEY", raising=False)
    import pytest
    with pytest.raises(SystemExit):
        h2h._key()
