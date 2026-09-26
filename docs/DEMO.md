# Demo runbook

The stage story in one line: **their builder gets 30 minutes and then a human; ours ships in
minutes, verified, with receipts — on the sites that break theirs.**

Total slot: aim for 6 minutes of talking over 2 live runs + 2 recorded beats.

## Run of show

| # | Beat | What's on screen | Line to land |
|---|---|---|---|
| 1 | Problem (30s) | Wire catalog page: "submit a request; most ship within days" | "966 sites, hand-queued long tail. We built the machine that writes the catalog." |
| 2 | Live forge (3m) | Forge Board on **BMTC** (or RedBus): stages tick, tool calls stream, spec appears, verifier checks go green | "No HTML parsing — it found the site's own JSON API and bound to it. One HTTP call at runtime, no browser, no proxy." |
| 3 | Boss fight (recorded, 1m) | **CPCB** run: obfuscated bundle flashes on screen, then the trace, then the decoded schema | "Obfuscated Angular, AES-encrypted API bodies, keys buried in the bundle. A description-to-scraper builder can't read this. The network trace doesn't care." |
| 4 | Head-to-head (30s) | `head2head.py report` timeline vs our `bench/results.csv` row for the same site | "Same URL, submitted to Wire's own builder at HH:MM. Here's both clocks." |
| 5 | Honest failure (30s) | **VTU** run ending in `requires_human_input` at the captcha wall, partial spec emitted | "When we can't ship, we say why and how far we got. Never a silent `failed`." |
| 6 | Breakthrough table (30s) | Results page: previous Opus vs 5.5, same sites, same judge | "Same pipeline, same verifier. This loop is what the last model couldn't hold onto." |

## Scorecard slide (works whatever their builder does)

| Axis | Wire build-request | Wire Forge |
|---|---|---|
| Time to a usable action | queue (mins–days) | live on stage |
| What ships | a scraper (browser + proxy per call) | the site's own JSON endpoint (one HTTP call) |
| Survives a redesign | no — "we patch upstream" | usually — internal APIs outlive UIs |
| Evidence | `pending → success/failed` | trace → endpoints → schema → test → independent verdict |
| On failure | silent `failed` | structured diagnosis + partial spec |

## Rules

- **Tone**: "we built ON Anakin, this is Wire + Forge" — they're a sponsor, the pitch is their missing feature, not a dunk.
- Every number quoted comes from `bench/results.csv` / `bench/head2head/*.jsonl`. If it's not in a file, it isn't said on stage.
- Live demo needs exactly two things working: the Forge Board and one Level 1–2 site. Everything else has a recording (issue #9).
- Dry-run the whole thing once on a phone hotspot before demo day.

## Pre-demo checklist

- [ ] `bench/results.csv` committed with at least one verified pair per level (issue #4)
- [ ] Head-to-head fired ≥ a day early so the timeline has length (issue #6, `scripts/head2head.py`)
- [ ] Recordings done and playable offline (issue #9)
- [ ] Board presets load, passcode set, API key on the demo laptop
- [ ] One rehearsed fallback: if live run stalls past 5 min, cut to the recording, keep talking
