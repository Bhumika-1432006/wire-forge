# Wire Forge

Auto-generate [Anakin Wire](https://anakin.io/products/wire) actions from any URL, powered by Claude Opus 5.5.

The Wire catalog covers ~965 sites, and every new site is hand-built. Wire Forge turns that into minutes:
give it a URL and a goal, and it returns a tested, verified Wire action.

```
URL + goal
  → forge agent drives a real browser (Anakin Browser API, or local Chromium)
  → records the site's own XHR/fetch traffic
  → finds the JSON endpoints, proves them with direct HTTP calls
  → emits a Wire action: spec.json + action.py + auto-generated test
  → the action is run immediately and checked against its return schema
  → an independent verifier agent (fresh browser, no shared reasoning) runs it
    with its own params and compares the output with what the rendered page shows
  → rejected? the verifier's report goes back to the forge to self-correct
```

Write actions (add to cart) are verified by loading the action's own session cookies into the
verifier's browser and checking that the cart page shows the item. Checkout, payment and order
endpoints are blocked in both the probe tool and the action harness.

## Setup

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"      # .venv/bin/pip on macOS/Linux
.venv/Scripts/python -m playwright install chromium
cp .env.example .env                       # add ANTHROPIC_API_KEY, optionally ANAKIN_API_KEY
```

## Run

```bash
# one action, with Opus 5.5
python -m wireforge forge https://www.snitch.com --goal "add a shirt in a given size to the cart"

# the Breakthrough demo: same site, previous Opus first, then Opus 5.5
python -m wireforge compare https://www.snitch.com --goal "add a shirt in a given size to the cart"
```

Each run writes `out/<site>__<model>__<time>/` with the action (`action/spec.json`, `action.py`,
`test_action.py`), the full transcript, the verifier's verdict, and appends a row to
`bench/results.csv`. The verifier is always Opus 5.5, so both models are judged by the same judge.

## Demo ladder

| Level | Site (not in the Wire catalog) | What makes it hard |
|---|---|---|
| 1 | BMTC, VTU results | single endpoint |
| 2 | RedBus, IRCTC | chained calls, ids from one response feed the next |
| 3 | Myntra, MakeMyTrip | pagination, nested payloads, session-bound APIs |
| 4 | Snitch, boAt, Mokobara (add to cart) | write action: variant resolution, session, read-back proof |

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the pipeline diagram, module map, contracts and open tasks.

## Tests

```bash
python -m pytest        # offline: capture, harness, spec validation, checkout guard
```
