"""The forge agent: explores a site, finds its own JSON endpoints, emits a Wire action."""

from __future__ import annotations

import json
from pathlib import Path

from .agent import Agent, Tool
from .browser import BrowserSession
from .spec import check_output, package, run_action, validate_spec
from .tools import B, S, _obj, browser_tools

SYSTEM = """You are Wire Forge. You turn a website into a Wire action: a small, reliable Python function \
that calls the site's own backend endpoints directly, with no browser, and returns structured JSON.

How to work:
1. Open the URL and use the site like a person would to accomplish the goal, so the site fires its real \
XHR/fetch calls. Use snapshot, then click/fill/select. Watch network_log after each step.
2. Find the endpoint(s) that carry the data or perform the change. Read them with network_detail. \
Also check embedded_json; some sites ship their data inline.
3. Prove your understanding with http_request before writing code: change a parameter and confirm the \
response changes as expected. Work out which headers, cookies, tokens (CSRF, session, API keys embedded \
in the page) are actually required, and where the action can obtain them itself at run time.
4. Call emit_action. It runs your code right away and reports errors or schema violations. Fix and \
re-emit until it passes, then call finish.

Rules for the action code:
- Define exactly `def run(params: dict, client: httpx.Client) -> dict`. Use only `client` for HTTP \
(it is pre-configured with a browser user agent and a cookie jar) plus the Python standard library, httpx, re, json.
- Never hard-code session cookies or tokens copied from your browser. If the site needs a token or a \
session, fetch it inside run() (for example GET the home page first, then parse the token).
- Apply defaults for optional params. Raise a clear exception when the site returns an error.
- Return real values from the endpoint, never placeholders. Keep the output compact and useful.
- Write actions (type "write") change state on the site, such as adding an item to a cart. After the \
change, read the resulting state back from the site (for example GET the cart) and return it, so the \
result proves the change happened. Never go to checkout, never pay, never place an order.

Rules for the spec:
- action_id is `<site>_<verb>_<noun>` in snake_case. Parameters use Wire types: string, integer, number, boolean.
- return_schema is a strict JSON Schema of your output that lists required fields and their types, so \
a broken action fails the test instead of passing silently.
- test_params are realistic values that should work right now.
"""

EMIT_SCHEMA = _obj({
    "action_id": S,
    "name": S,
    "description": S,
    "type": {"type": "string", "enum": ["read", "write"]},
    "tags": {"type": "array", "items": S},
    "parameters": {"type": "array", "items": _obj({
        "name": S, "type": {"type": "string", "enum": ["string", "integer", "number", "boolean"]},
        "required": B, "default": {}, "description": S,
    }, ["name", "type", "required", "description"])},
    "return_schema": {"type": "object"},
    "endpoints": {"type": "array", "items": S, "description": "METHOD URL-pattern of each endpoint used"},
    "code": S,
    "test_params": {"type": "object"},
}, ["action_id", "name", "description", "type", "parameters", "return_schema", "code", "test_params"])


class Forge:
    def __init__(self, url: str, goal: str, model: str, run_dir: Path, browser: BrowserSession):
        self.url, self.goal, self.run_dir = url, goal, run_dir
        self.action_dir = run_dir / "action"
        self.passed = False
        self.emits = 0
        self.spec: dict | None = None
        tools = browser_tools(browser) + [
            Tool("emit_action", "Package the Wire action, run it once with test_params, and report the result.",
                 EMIT_SCHEMA, self.emit),
            Tool("finish", "Call after emit_action passed. Summarise the endpoints and what the action does.",
                 _obj({"summary": S}, ["summary"]), self.finish),
        ]
        self.agent = Agent("forge", model, SYSTEM, tools, run_dir / "transcript.jsonl")

    def emit(self, code: str, test_params: dict, **spec) -> str:
        self.emits += 1
        spec["source_url"] = self.url
        errs = validate_spec(spec)
        if errs:
            self.passed = False
            return "Spec rejected:\n- " + "\n- ".join(errs)
        package(self.action_dir, spec, code, test_params)
        out = run_action(self.action_dir / "action.py", test_params)
        errs = check_output(spec, out)
        self.spec = spec
        self.passed = not errs
        (self.run_dir / "last_run.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        if errs:
            return "Action FAILED:\n" + "\n".join(errs)
        preview = json.dumps(out["result"], default=str)[:2500]
        return f"Action PASSED schema check in {out['elapsed_s']}s. Output:\n{preview}"

    def finish(self, summary: str) -> str:
        if not self.passed:
            return "Refused: the last emit_action did not pass. Fix it first."
        self.agent.finished = True
        return "Done."

    def run(self):
        task = f"URL: {self.url}\nGoal: {self.goal}\nBuild the Wire action for this goal."
        return self.agent.run(task)

    def repair(self, report: str):
        self.agent.finished = False
        return self.agent.nudge(
            "An independent verifier checked your action against the live site and rejected it:\n"
            f"{report}\nInvestigate, fix the action, re-emit it, then call finish."
        )
