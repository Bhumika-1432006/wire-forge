"""Runs one generated action in a separate process.

Usage: python -m wireforge.harness <action.py> <params.json> <out.json>

Every generated action exposes `run(params: dict, client: httpx.Client) -> dict`.
The harness owns the client, so after a write action it can export the session
cookies and the verifier can open the same cart in a real browser.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
import traceback

import httpx

from .probe import UA, blocked


def _guard(request: httpx.Request) -> None:
    if reason := blocked(str(request.url)):
        raise RuntimeError(reason)


def main() -> None:
    action_path, params_path, out_path = sys.argv[1:4]
    params = json.loads(open(params_path, encoding="utf-8").read())
    out: dict = {"ok": False}
    t0 = time.time()
    client = httpx.Client(
        follow_redirects=True, timeout=30, headers={"user-agent": UA},
        event_hooks={"request": [_guard]},
    )
    try:
        spec = importlib.util.spec_from_file_location("wf_action", action_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(mod)
        out["result"] = mod.run(params, client)
        out["ok"] = True
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["traceback"] = traceback.format_exc()[-3000:]
    finally:
        out["elapsed_s"] = round(time.time() - t0, 2)
        out["cookies"] = [
            {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path or "/"}
            for c in client.cookies.jar
        ]
        client.close()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=str)


if __name__ == "__main__":
    main()
