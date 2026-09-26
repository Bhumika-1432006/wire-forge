"""trace -> endpoint -> schema -> test -> verify -> self-correct, with one CSV row per run."""

from __future__ import annotations

import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from . import config
from .browser import BrowserSession
from .forge import Forge
from .verifier import Verifier

CSV_FIELDS = [
    "timestamp", "site", "goal", "model", "outcome", "action_id", "type", "emits", "repair_rounds",
    "forge_turns", "forge_tool_calls", "forge_tool_errors", "input_tokens", "output_tokens",
    "verifier_model", "verifier_checks", "verifier_matched", "wall_s", "browser", "run_dir",
]


def _slug(url: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", urlparse(url).netloc.lower()).strip("-")


def forge_action(url: str, goal: str, model: str, verifier_model: str | None = None,
                 headless: bool = True) -> dict:
    verifier_model = verifier_model or config.FORGE_MODEL
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = config.OUT_DIR / f"{_slug(url)}__{model}__{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    verdict: dict = {"passed": False, "checks": [], "summary": "not verified"}
    repairs = 0

    with BrowserSession(headless=headless) as browser:
        backend = browser.backend
        forge = Forge(url, goal, model, run_dir, browser)
        stats = forge.run()
        while True:
            if not forge.passed:
                outcome = "no_working_action"
                break
            # A fresh browser for the verifier: it must not inherit the forge's session.
            with browser.isolated() as vb:
                verifier = Verifier(forge.action_dir, verifier_model, run_dir, vb)
                verifier.run()
                verdict = verifier.verdict or verdict
            if verdict["passed"]:
                outcome = "verified"
                break
            if repairs >= config.MAX_REPAIR_ROUNDS:
                outcome = "rejected_by_verifier"
                break
            repairs += 1
            print(f"\n=== verifier rejected; repair round {repairs} ===\n", flush=True)
            stats = forge.repair(json.dumps(verdict, indent=1))

    summary = {
        "site": url, "goal": goal, "model": model, "outcome": outcome,
        "action_id": (forge.spec or {}).get("action_id", ""), "type": (forge.spec or {}).get("type", ""),
        "emits": forge.emits, "repair_rounds": repairs,
        "forge_turns": stats.turns, "forge_tool_calls": stats.tool_calls, "forge_tool_errors": stats.tool_errors,
        "input_tokens": stats.input_tokens, "output_tokens": stats.output_tokens,
        "verifier_model": verifier_model, "verifier_checks": len(verdict.get("checks", [])),
        "verifier_matched": sum(1 for c in verdict.get("checks", []) if c.get("match")),
        "wall_s": round(time.time() - t0, 1), "browser": backend, "run_dir": str(run_dir.relative_to(config.ROOT)),
    }
    (run_dir / "verdict.json").write_text(json.dumps(verdict, indent=1), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    _append_csv(summary)
    return summary


def _append_csv(row: dict) -> None:
    path: Path = config.RESULTS_CSV
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new:
            w.writeheader()
        w.writerow({"timestamp": datetime.now().isoformat(timespec="seconds"), **row})
