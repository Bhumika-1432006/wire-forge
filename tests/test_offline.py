"""Checks for the parts of Wire Forge that need no API key: capture, harness, spec, guardrails."""

import functools
import http.server
import threading
from pathlib import Path

import pytest

from wireforge.browser import BrowserSession
from wireforge.probe import http_request
from wireforge.spec import check_output, run_action, validate_spec

SITE = Path(__file__).parent / "site"

GOOD_SPEC = {
    "action_id": "demo_search_stops", "name": "Search stops", "description": "d", "type": "read",
    "parameters": [{"name": "q", "type": "string", "required": True, "description": "stop name"}],
    "return_schema": {"type": "object", "required": ["stops"],
                      "properties": {"stops": {"type": "array", "items": {"type": "string"}}}},
}


@pytest.fixture(scope="module")
def site_url():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_browser_captures_fetch_triggered_by_ui(site_url):
    with BrowserSession() as b:
        b.goto(site_url + "/index.html")
        snap = b.snapshot()
        inp = next(line.split()[0] for line in snap.splitlines() if "stop name" in line)
        btn = next(line.split()[0] for line in snap.splitlines() if '"Search"' in line)
        b.fill(inp, "maj")
        b.click(btn)
        log = b.network_log(contains="stops.json")
        assert "q=maj" in log
        idx = int(log.split()[0].lstrip("#"))
        detail = b.network_detail(idx)
        assert '"x-client": "demo"' in detail and "Majestic" in detail
        assert "Majestic" in b.page_text()


def test_isolated_session_does_not_share_cookies(site_url):
    with BrowserSession() as b:
        b.goto(site_url + "/index.html")
        b.add_cookies([{"name": "sid", "value": "1", "url": site_url}])
        with b.isolated() as v:
            assert v.cookies() == []
        assert b.cookies()[0]["name"] == "sid"


def test_harness_runs_action_and_schema_check(tmp_path, site_url):
    action = tmp_path / "action.py"
    action.write_text(
        "def run(params, client):\n"
        f"    d = client.get('{site_url}/api/stops.json', params={{'q': params['q']}}).json()\n"
        "    return {'stops': [s['name'] for s in d['stops']]}\n"
    )
    out = run_action(action, {"q": "maj"})
    assert out["ok"], out
    assert check_output(GOOD_SPEC, out) == []
    bad = dict(GOOD_SPEC, return_schema={"type": "object", "required": ["count"]})
    assert check_output(bad, out)


def test_harness_blocks_checkout(tmp_path):
    action = tmp_path / "action.py"
    action.write_text("def run(params, client):\n    client.post('https://example.com/checkout')\n    return {}\n")
    out = run_action(action, {})
    assert not out["ok"] and "Refused" in out["error"]
    assert "Refused" in http_request("POST", "https://shop.example/cart/checkout")


def test_spec_validation():
    assert validate_spec(GOOD_SPEC) == []
    errs = validate_spec(dict(GOOD_SPEC, action_id="Bad Id", type="delete",
                              return_schema={"type": "object"}))
    assert len(errs) == 3


def test_check_browser_passes_on_local_chromium(site_url):
    from wireforge.browsercheck import check_browser

    results = check_browser(site_url + "/index.html")
    assert all(ok for _, ok, _ in results), results
    assert {n for n, _, _ in results} >= {"connect", "isolated session", "forge cookies survive"}
