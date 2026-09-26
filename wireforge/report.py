"""python -m wireforge.report   turn bench/results.csv into docs/RESULTS.md (never hand-edited)."""

from __future__ import annotations

import csv
from pathlib import Path

from . import config

OUT_MD = config.ROOT / "docs" / "RESULTS.md"
COLS = ("model", "outcome", "emits", "repair_rounds", "forge_turns", "output_tokens", "wall_s")


def load(path: Path = config.RESULTS_CSV) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _latest_per_model(rows: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for r in rows:  # CSV is append-only, so the last row for a model is its newest run
        latest[r["model"]] = r
    return latest


def render(rows: list[dict]) -> str:
    lines = ["# Results", "", "Generated from `bench/results.csv` by `python -m wireforge.report`. Do not edit by hand.", ""]
    if not rows:
        return "\n".join(lines + ["No runs recorded yet."]) + "\n"
    sites: dict[str, list[dict]] = {}
    for r in rows:
        sites.setdefault(r["site"], []).append(r)
    for site, site_rows in sites.items():
        lines += [f"## {site}", "", f"Goal: {site_rows[-1]['goal']}", "",
                  "| " + " | ".join(COLS) + " |", "|" + "---|" * len(COLS)]
        for r in _latest_per_model(site_rows).values():
            lines.append("| " + " | ".join(r.get(c, "") for c in COLS) + " |")
        models = {r["model"] for r in site_rows}
        if config.BASELINE_MODEL not in models or config.FORGE_MODEL not in models:
            lines += ["", "_Incomplete: needs both a baseline and a 5.5 run._"]
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render(load()), encoding="utf-8")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
