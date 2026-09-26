"""Put a catalog Wire action in front of our verifier: one judge for everyone.

`wireforge verify-wire <action_id> --site <url>` wraps an action from Anakin's public catalog
(read-only actions run keylessly via POST /v1/wire-run) in the same action-dir layout the forge
emits, and hands it to the independent verifier. The verifier then runs it twice and diffs its
output against the rendered page, exactly as it does for our own actions. The verdict lands in
the usual run dir; nothing about the verifier is special-cased.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import httpx

from . import config

API = "https://api.anakin.io/v1"

ACTION_TEMPLATE = '''\
"""Wire catalog action {action_id}, run through Anakin's keyless read-only endpoint."""


def run(params: dict, client) -> dict:
    r = client.post("{api}/wire-run", json={{"action_id": "{action_id}", "params": params}})
    r.raise_for_status()
    body = r.json()
    if body.get("status") not in (None, "completed"):
        raise RuntimeError(f"wire-run status={{body.get('status')}}: {{json.dumps(body)[:500]}}")
    return body.get("data", body.get("result"))


import json  # noqa: E402  (used in the error path above)
'''


def resolve(action_id: str, catalog: str = "") -> dict:
    """Find the action's parameter schema in the public catalog (no key needed).

    /wire/resolve matches intent text, not ids, so given a catalog slug we read the catalog's
    full action list instead; otherwise we resolve on the id with underscores as spaces.
    """
    with httpx.Client(timeout=60) as c:
        if catalog:
            r = c.get(f"{API}/wire/catalog/{catalog}")
            r.raise_for_status()
            for a in r.json().get("actions", []):
                if a.get("action_id") == action_id:
                    req = [p for p in a.get("parameters", []) if p.get("required")]
                    opt = [p for p in a.get("parameters", []) if not p.get("required")]
                    return {"action_id": action_id, "catalog": catalog,
                            "credits": a.get("credits_per_call"),
                            "params": {"required": req, "optional": opt}}
        else:
            r = c.get(f"{API}/wire/resolve", params={"q": action_id.replace("_", " ")})
            r.raise_for_status()
            for hit in r.json().get("results", []):
                if hit.get("action_id") == action_id:
                    return hit
    where = f"catalog {catalog!r}" if catalog else "GET /v1/wire/resolve (pass --catalog <slug> to search a catalog directly)"
    raise SystemExit(f"action {action_id!r} not found in {where}")


def build_action_dir(action_id: str, site: str, run_dir: Path, hit: dict) -> Path:
    """Write spec.json / action.py / test_params.json in the exact layout the forge emits."""
    params = hit.get("params") or {}
    parameters = [
        {"name": p["name"], "type": p.get("type", "string"), "required": req,
         "description": f"default: {p.get('default')}" if p.get("default") is not None else ""}
        for req, group in ((True, params.get("required", [])), (False, params.get("optional", [])))
        for p in group
    ]
    test_params = {p["name"]: p.get("default") for p in params.get("required", [])
                   if p.get("default") is not None}
    spec = {
        "action_id": action_id, "type": "read", "mode": "wire-catalog",
        "name": f"Wire catalog: {action_id}",
        "description": f"Catalog {hit.get('catalog', '?')} action, {hit.get('credits', '?')} credits/call. "
                       f"Source site: {site}. Executed via Anakin's keyless wire-run endpoint.",
        "parameters": parameters,
        # The catalog does not publish a return schema keylessly, so schema checking is
        # deliberately permissive here: the verifier judges against the rendered page instead.
        "return_schema": {"type": ["object", "array", "null"]},
        "endpoints": [f"POST {API}/wire-run ({action_id})"],
    }
    d = run_dir / "action"
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
    (d / "action.py").write_text(ACTION_TEMPLATE.format(api=API, action_id=action_id), encoding="utf-8")
    (d / "test_params.json").write_text(json.dumps(test_params, indent=1), encoding="utf-8")
    return d


def verify_wire(action_id: str, site: str, verifier_model: str | None = None, catalog: str = "") -> dict:
    from .browser import BrowserSession  # imported here: heavy, and offline tests never need it
    from .verifier import Verifier

    verifier_model = verifier_model or config.FORGE_MODEL
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = config.OUT_DIR / f"wire-catalog__{action_id}__{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    hit = resolve(action_id, catalog)
    action_dir = build_action_dir(action_id, site, run_dir, hit)
    (run_dir / "request.json").write_text(json.dumps(
        {"url": site, "goal": f"verify catalog action {action_id}", "model": "anakin-wire-catalog",
         "verifier_model": verifier_model}), encoding="utf-8")

    t0 = time.time()
    with BrowserSession(headless=True) as browser:
        verifier = Verifier(action_dir, verifier_model, run_dir, browser)
        verifier.run()
    verdict = verifier.verdict or {"passed": False, "checks": [], "summary": "no verdict"}
    (run_dir / "verdict.json").write_text(json.dumps(verdict, indent=1), encoding="utf-8")
    summary = {"system": "anakin-wire-catalog", "action_id": action_id, "site": site,
               "passed": verdict["passed"], "checks": len(verdict.get("checks", [])),
               "matched": sum(1 for c in verdict.get("checks", []) if c.get("match")),
               "wall_s": round(time.time() - t0, 1), "run_dir": run_dir.name}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary
