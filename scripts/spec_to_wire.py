"""Hand a forged action to Wire (issue #7).

Wire's public API has no way to upload a ready spec or code: POST /v1/wire/build-request
takes only website_url + goal. So the best channel is a goal written from our verified
spec.json: the exact endpoints, parameters and return shape the forge already proved.

    python scripts/spec_to_wire.py out/<run>/action/spec.json            # print the goal
    python scripts/spec_to_wire.py out/<run>/action/spec.json --submit   # submit (25 credits)

The build is then tracked with scripts/head2head.py (watch / report).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import head2head  # noqa: E402  (same folder; reuses its client, logging and polling)


def goal_from_spec(spec: dict) -> str:
    params = "; ".join(
        f"{p['name']} ({p['type']}{', required' if p.get('required') else ''}): {p['description']}"
        for p in spec.get("parameters", [])
    )
    returns = ", ".join(spec.get("return_schema", {}).get("properties", {}).keys())
    endpoints = "; ".join(spec.get("endpoints", []))
    return (
        f"{spec['description']} "
        f"Parameters: {params}. "
        f"Use the site's own endpoints: {endpoints}. "
        f"Return: {returns}."
    )[:2000]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", type=Path)
    ap.add_argument("--submit", action="store_true")
    args = ap.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    goal = goal_from_spec(spec)
    print(goal)
    if args.submit:
        sys.argv = ["head2head.py", "submit", spec["source_url"], "--goal", goal]
        head2head.main()


if __name__ == "__main__":
    main()
