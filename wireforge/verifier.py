"""The verifier: a separate agent, with a fresh browser and no access to the forge's reasoning,
that runs the action and checks its output against what the rendered site actually shows."""

from __future__ import annotations

import json
from pathlib import Path

from .agent import Agent, Tool
from .browser import BrowserSession
from .spec import check_output, run_action
from .tools import B, S, _obj, browser_tools

SYSTEM = """You are the Wire Forge verifier. Someone else wrote a Wire action: a Python function that calls a \
website's backend directly. Your job is to decide whether its output is TRUE, by comparing it with what the \
real website shows a human in a browser. Be skeptical; a plausible-looking action can return stale, wrong, \
or made-up data, or silently ignore its parameters.

Procedure:
1. Run the action with its test_params (run_action).
2. Run it again with at least one different, realistic set of params you choose, to catch actions that ignore \
their inputs. For write actions, use a different item or quantity.
3. Open the site in the browser and look at the same thing a person would (page_text, snapshot, click, fill). \
Compare concrete values: names, prices, counts, ids, dates. Spot-check at least 3 values per run.
4. For write actions: call open_with_action_session on the page that shows the changed state (the cart, for \
example). This loads the action's own session cookies into your browser. Confirm the page shows the change, \
such as the item and quantity the action reported. If the site keeps the state only in local storage and the \
page cannot show it, say so and judge from the site's own state endpoint instead.
5. Call submit_verdict. For a write action, set write_persisted to true only if you saw the change stored by the \
site itself (its page or its own endpoint, read with the action's session). If the action only computed a result \
and nothing was stored on the site, set it to false, even if every value it returned is correct. \
Pass only if every check matched. Small differences a live site can explain, such as \
a price that changed between runs, are fine; say so in the check's note.

Never go to checkout, pay, or place an order."""

VERDICT_SCHEMA = _obj({
    "passed": B,
    "checks": {"type": "array", "items": _obj(
        {"what": S, "action_value": S, "page_value": S, "match": B, "note": S},
        ["what", "action_value", "page_value", "match"])},
    "summary": S,
    "write_persisted": {"type": "boolean", "description": "Write actions only: did you see the change stored by the site?"},
}, ["passed", "checks", "summary"])


class Verifier:
    def __init__(self, action_dir: Path, model: str, run_dir: Path, browser: BrowserSession):
        self.action_dir = action_dir
        self.browser = browser
        self.spec = json.loads((action_dir / "spec.json").read_text(encoding="utf-8"))
        self.last_cookies: list[dict] = []
        self.runs = 0
        self.verdict: dict | None = None
        tools = browser_tools(browser) + [
            Tool("run_action", "Run the Wire action with the given params and return its output.",
                 _obj({"params": {"type": "object"}}, ["params"]), self.run_action),
            Tool("open_with_action_session",
                 "Load the cookies from the most recent run_action into the browser, then open this URL.",
                 _obj({"url": S}, ["url"]), self.open_with_session),
            Tool("submit_verdict", "Submit the final verdict with every check you made.",
                 VERDICT_SCHEMA, self.submit),
        ]
        self.agent = Agent("verifier", model, SYSTEM, tools, run_dir / "transcript.jsonl")

    def run_action(self, params: dict) -> str:
        self.runs += 1
        out = run_action(self.action_dir / "action.py", params)
        self.last_cookies = out.get("cookies", [])
        errs = check_output(self.spec, out)
        head = "OK" if not errs else "FAILED: " + "; ".join(errs)
        return f"{head}\nresult: {json.dumps(out.get('result'), default=str)[:5000]}"

    def open_with_session(self, url: str) -> str:
        if not self.last_cookies:
            return "No cookies from a previous run_action. Run the action first."
        cookies = []
        for c in self.last_cookies:
            cookie = {"name": c["name"], "value": c["value"]}
            if c.get("domain"):
                cookie.update(domain=c["domain"], path=c.get("path") or "/")
            else:
                cookie["url"] = url
            cookies.append(cookie)
        self.browser.add_cookies(cookies)
        return self.browser.goto(url)

    def submit(self, passed: bool, checks: list, summary: str, write_persisted: bool | None = None) -> str:
        if self.spec.get("type") == "write" and write_persisted is None:
            return "Refused: this is a write action; say whether the change was stored by the site (write_persisted)."
        if self.runs < 2:
            return "Refused: run the action at least twice (test_params plus your own params) before judging."
        if passed and not any(c.get("match") for c in checks):
            return "Refused: a pass needs at least one matched check against the page."
        # A mismatch may only coexist with a pass when the verifier wrote down why it is acceptable.
        if passed and any(not c.get("match") and not (c.get("note") or "").strip() for c in checks):
            passed = False
        self.verdict = {"passed": passed, "checks": checks, "summary": summary, "write_persisted": write_persisted}
        self.agent.finished = True
        return "Verdict recorded."

    def run(self):
        spec_text = json.dumps(self.spec, indent=1)
        code = (self.action_dir / "action.py").read_text(encoding="utf-8")
        params = (self.action_dir / "test_params.json").read_text(encoding="utf-8")
        task = f"Spec:\n{spec_text}\n\ntest_params:\n{params}\n\nCode:\n```python\n{code}\n```\nVerify this action."
        stats = self.stats = self.agent.run(task, max_turns=40)
        if self.verdict is None:
            self.verdict = {"passed": False, "checks": [], "summary": f"verifier stopped without a verdict ({stats.stop})"}
        return stats
