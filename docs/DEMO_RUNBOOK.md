# Demo runbook and backup video checklist

Companion to issue #9. Venue Wi-Fi will fail, so every stage moment has a pre-recorded twin.

## Before recording

1. `python -m pytest` is green and `python -m wireforge check-browser` passes (or you know which backend you will use).
2. `.env` has `ANTHROPIC_API_KEY` (and `ANAKIN_API_KEY` if you show the Anakin browser). Never show `.env` on screen.
3. Clear `out/` so the run directories on screen are only the ones being shown. Do not touch `bench/results.csv` by hand.
4. Terminal font 18pt+, dark background, one window for the terminal and one for the Forge Board.
5. Record at 1080p or higher, at the real speed. Do not fake or edit the agent's steps.

## What to record (each take is its own file)

| # | Take | Command | What must be visible |
|---|---|---|---|
| 1 | Verified run, headliner site | `python -m wireforge forge <url> --goal "<goal>"` | Forge steps, the emit passing its schema check, the verifier's checks, final `verified` row |
| 2 | Baseline fails or drifts | `python -m wireforge compare <url> --goal "<goal>"` | The previous model's outcome next to Opus 5.5's, same site, same goal |
| 3 | Head-to-head with Anakin build-request | see #6 | Submit time and every status change with timestamps |
| 4 | VTU honest failure | `python -m wireforge forge <vtu-url> --goal "<goal>"` | The verifier rejecting a partial spec, and the pipeline saying so |

Rules: numbers shown in the video must come from `bench/results.csv` (or `python -m wireforge.report` output). If a run goes badly, keep the take: an honest failure is a feature.

## After recording

- Keep the raw files and one cut under 3 minutes, stored outside the repo. Add a link in the README.
- Play the cut once with the sound off: it should still make sense from the terminal and Board alone.

## Dry run on a phone hotspot

1. Connect the laptop to the phone hotspot only (Wi-Fi off elsewhere).
2. Run the Level 1 demo end to end and note wall time and data used (phone data counter before/after).
3. If it takes more than the demo slot allows, switch the stage plan to: play take 1, then run only the live call of the finished action.

## Stage fallback order

1. Live run. 2. If the network is slow or dead at minute 1, play take 1 and narrate. 3. Never wait on a hung run: cut to the video.
