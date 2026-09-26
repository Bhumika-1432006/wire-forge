"""wireforge forge <url> --goal "..."      build one action with the model under test
wireforge compare <url> --goal "..."    same site with the baseline model, then the new one
wireforge check-browser [url]           verify the browser backend (Anakin CDP if ANAKIN_API_KEY is set)"""

from __future__ import annotations

import argparse
import json

from . import config
from .pipeline import forge_action


def main() -> None:
    ap = argparse.ArgumentParser(prog="wireforge")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("forge", "compare"):
        p = sub.add_parser(name)
        p.add_argument("url")
        p.add_argument("--goal", required=True, help="what the action should do, in plain words")
        p.add_argument("--headed", action="store_true", help="show the local browser window")
        if name == "forge":
            p.add_argument("--model", default=config.FORGE_MODEL)
    cb = sub.add_parser("check-browser")
    cb.add_argument("url", nargs="?", default="https://example.com")
    args = ap.parse_args()

    if args.cmd == "check-browser":
        from .browsercheck import main as check_main
        raise SystemExit(check_main(args.url))

    if args.cmd == "forge":
        result = forge_action(args.url, args.goal, args.model, headless=not args.headed)
        print(json.dumps(result, indent=1))
        return

    rows = []
    for model in (config.BASELINE_MODEL, config.FORGE_MODEL):
        print(f"\n######## {model} ########\n", flush=True)
        rows.append(forge_action(args.url, args.goal, model, headless=not args.headed))
    print("\nmodel               outcome               emits repairs turns  tokens(out)  wall_s")
    for r in rows:
        print(f"{r['model']:<19} {r['outcome']:<21} {r['emits']:>5} {r['repair_rounds']:>7} "
              f"{r['forge_turns']:>5} {r['output_tokens']:>11} {r['wall_s']:>7}")


if __name__ == "__main__":
    main()
