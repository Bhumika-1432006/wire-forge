"""python -m wireforge check-browser [url]   verify the browser backend does what the pipeline needs.

Run it once with ANAKIN_API_KEY set to test Anakin's Browser API over CDP; without a key it tests local Chromium.
"""

from __future__ import annotations

from urllib.parse import urlparse

from .browser import BrowserSession

DEFAULT_URL = "https://example.com"


def check_browser(url: str = DEFAULT_URL) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))

    try:
        with BrowserSession() as b:
            record("connect", True, b.backend)
            b.goto(url)
            captured = [e for e in b.net if e.resource_type == "document"]
            record("network capture (document)", bool(captured), f"{len(b.net)} requests captured")
            origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
            b.add_cookies([{"name": "wf_check", "value": "1", "url": origin}])
            with b.isolated() as v:
                mode = "shared context, cookies cleared" if getattr(v, "_shared_context", False) else "own context"
                record("isolated session", True, mode)
                record("verifier has no forge cookies", not any(c["name"] == "wf_check" for c in v.cookies()))
            record("forge cookies survive", any(c["name"] == "wf_check" for c in b.cookies()))
    except Exception as e:  # report instead of crashing so the remaining checks are visible
        record("browser session", False, f"{type(e).__name__}: {e}")
    return results


def main(url: str = DEFAULT_URL) -> int:
    results = check_browser(url)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    return 0 if all(ok for _, ok, _ in results) else 1
