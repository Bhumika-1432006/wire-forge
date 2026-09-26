"""python -m wireforge.scorecard   render bench/head2head/*.json receipts into docs/HEAD2HEAD.md.

A receipt is one system's run on one site:
  {"system": "anakin-build-request" | "wire-forge", "site": "...", "goal": "...",
   "events": [{"status": "submitted", "ts": "2026-09-26T11:00:00"}, ..., {"status": "shipped", "ts": "..."}],
   "action_type": "scraper" | "native-endpoint", "cost_per_call": "...",
   "verification": "...", "failure": "..."}
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import config

RECEIPTS_DIR = config.ROOT / "bench" / "head2head"
OUT_MD = config.ROOT / "docs" / "HEAD2HEAD.md"
SHIPPED = "shipped"
COLS = ("system", "time to ship", "action type", "cost / call", "verification", "failure transparency")


def load(directory: Path = RECEIPTS_DIR) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))] if directory.is_dir() else []


def time_to_ship(receipt: dict) -> str:
    events = receipt.get("events", [])
    if not events:
        return "n/a"
    start = datetime.fromisoformat(events[0]["ts"])
    end = next((datetime.fromisoformat(e["ts"]) for e in events if e["status"] == SHIPPED), None)
    if end is None:
        return f"not shipped (last status: {events[-1]['status']})"
    secs = int((end - start).total_seconds())
    return f"{secs // 60}m {secs % 60:02d}s"


def render(receipts: list[dict]) -> str:
    lines = ["# Head-to-head", "", "Generated from `bench/head2head/*.json` by `python -m wireforge.scorecard`. Do not edit by hand.", ""]
    if not receipts:
        return "\n".join(lines + ["No receipts recorded yet."]) + "\n"
    sites: dict[str, list[dict]] = {}
    for r in receipts:
        sites.setdefault(r["site"], []).append(r)
    for site, rs in sites.items():
        lines += [f"## {site}", "", f"Goal: {rs[0].get('goal', '')}", "",
                  "| " + " | ".join(COLS) + " |", "|" + "---|" * len(COLS)]
        for r in rs:
            cells = (r["system"], time_to_ship(r), r.get("action_type", "?"), r.get("cost_per_call", "?"),
                     r.get("verification", "none"), r.get("failure", "none reported"))
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render(load()), encoding="utf-8")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
