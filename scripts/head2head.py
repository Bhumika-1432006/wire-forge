"""Head-to-head receipts: fire Anakin's own builder on a URL and record every status change.

The demo compares Wire Forge against Wire's built-in `POST /v1/wire/build-request` on the same
site. This script produces the receipts for Anakin's side: it submits the build, then polls and
appends a timestamped row to bench/head2head/<domain>.jsonl on every status change, so the
timeline we show judges is reproducible from disk, not from memory.

Usage:
  python scripts/head2head.py submit <url> --goal "..."     # fire the build, start polling
  python scripts/head2head.py watch                          # resume polling all pending builds
  python scripts/head2head.py report                         # print a timeline per site

Needs ANAKIN_API_KEY in the environment or .env (claim credits with the sponsor coupon first).
Wire Forge's side of the comparison comes from bench/results.csv as usual.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

try:  # same convention as wireforge.config, but keep this script standalone
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

API = "https://api.anakin.io/v1"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "bench" / "head2head"
POLL_S = 30


def _key() -> str:
    key = os.getenv("ANAKIN_API_KEY", "")
    if not key:
        sys.exit("ANAKIN_API_KEY is not set. Claim credits (sponsor coupon) and add it to .env")
    return key


def _client() -> httpx.Client:
    return httpx.Client(headers={"X-API-Key": _key()}, timeout=60)


def _log_path(domain: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    return OUT / f"{domain.replace('.', '-')}.jsonl"


def _append(domain: str, event: str, **data) -> dict:
    row = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, **data}
    with _log_path(domain).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    print(f"[{row['t']}] {domain}: {event} {data.get('status', '')}", flush=True)
    _write_receipt(domain)
    return row


def _write_receipt(domain: str) -> None:
    """Mirror the JSONL audit log into the receipt schema wireforge.scorecard renders (#16).

    Anakin's terminal `success` becomes the scorecard's `shipped`; everything else keeps its name.
    """
    rows = _rows(_log_path(domain))
    events = []
    for r in rows:
        status = r.get("status") or r["event"]
        events.append({"status": "shipped" if status == "success" else status, "ts": r["t"]})
    goal = next((r.get("goal") for r in rows if r.get("goal")), "")
    receipt = {
        "system": "anakin-build-request", "site": f"https://{domain}", "goal": goal, "events": events,
        "action_type": "scraper", "cost_per_call": "25 credits/build; browser+proxy per call",
        "verification": "opaque (status only)",
        "failure": next((r["error"] for r in rows if r.get("error")), "none reported"),
    }
    (OUT / f"{domain.replace('.', '-')}__anakin.json").write_text(
        json.dumps(receipt, indent=1), encoding="utf-8")


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def submit(url: str, goal: str) -> None:
    domain = urlparse(url).netloc.removeprefix("www.")
    with _client() as c:
        r = c.post(f"{API}/wire/build-request", json={"website_url": url, "goal": goal})
        body = r.json()
        _append(domain, "submitted", http=r.status_code, goal=goal, response=body)
        if r.status_code == 409:  # ACTION_EXISTS is itself a finding worth keeping
            print("Similar action already exists; recorded. Re-run with a sharper goal or note it in the demo.")
            return
        r.raise_for_status()
    watch()


def watch() -> None:
    """Poll all builds that have not reached a terminal status; append a row per change."""
    with _client() as c:
        while True:
            r = c.get(f"{API}/wire/build-requests")
            r.raise_for_status()
            reqs = r.json().get("build_requests", r.json() if isinstance(r.json(), list) else [])
            pending = 0
            for br in reqs:
                domain = (br.get("domain") or "unknown").removeprefix("www.")
                path = _log_path(domain)
                last = next((x for x in reversed(_rows(path)) if "status" in x), None) if path.exists() else None
                if last is None and not path.exists():
                    continue  # not one of ours
                if br.get("status") not in ("success", "failed"):
                    pending += 1
                if not last or last.get("status") != br.get("status"):
                    _append(domain, "status_change", status=br.get("status"),
                            action_id=br.get("action_id"), error=br.get("error"), raw=br)
            if not pending:
                print("No pending builds left.")
                return
            time.sleep(POLL_S)


def report() -> None:
    if not OUT.exists():
        print("No head-to-head logs yet. Run `submit` first.")
        return
    for path in sorted(OUT.glob("*.jsonl")):
        rows = _rows(path)
        if not rows:
            continue
        start = next((r for r in rows if r["event"] == "submitted"), rows[0])
        end = next((r for r in reversed(rows) if r.get("status") in ("success", "failed")), None)
        t0 = datetime.fromisoformat(start["t"])
        print(f"\n== {path.stem}")
        for r in rows:
            dt = (datetime.fromisoformat(r["t"]) - t0).total_seconds()
            print(f"  +{dt/60:7.1f} min  {r['event']:<14} {r.get('status', '')} {r.get('error') or ''}")
        if end:
            mins = (datetime.fromisoformat(end["t"]) - t0).total_seconds() / 60
            print(f"  => {end['status']} after {mins:.1f} min")
        else:
            print("  => still pending")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("submit", help="fire a build-request and poll it")
    s.add_argument("url")
    s.add_argument("--goal", required=True)
    sub.add_parser("watch", help="resume polling pending builds")
    sub.add_parser("report", help="print the timeline per site")
    args = ap.parse_args()
    if args.cmd == "submit":
        submit(args.url, args.goal)
    elif args.cmd == "watch":
        watch()
    else:
        report()


if __name__ == "__main__":
    main()
