"""Check Wire Forge's browser layer against Anakin's Browser API (issue #2).

Needs ANAKIN_API_KEY. Costs about 1 credit per 2 minutes of browser time.

    python scripts/check_anakin_cdp.py [url]

Checks: connect over CDP, xhr/fetch capture, and that the verifier's isolated()
session does not see the forge session's cookies (new_context, or the
cleared-cookies fallback when the remote browser refuses new contexts).
"""

from __future__ import annotations

import sys
import time

from wireforge import config
from wireforge.browser import BrowserSession

URL = sys.argv[1] if len(sys.argv) > 1 else "https://aqicn.org/city/delhi/"


def main() -> int:
    if not config.ANAKIN_API_KEY:
        print("ANAKIN_API_KEY is not set")
        return 2
    ok = True
    t0 = time.time()
    with BrowserSession() as b:
        print(f"backend: {b.backend}  connect: {time.time() - t0:.1f}s")
        print(b.goto(URL))
        data_calls = [e for e in b.net if e.resource_type in ("xhr", "fetch")]
        with_body = [e for e in data_calls if e.body]
        print(f"capture: {len(b.net)} entries, {len(data_calls)} xhr/fetch, {len(with_body)} with a body")
        for e in with_body[:5]:
            print("   ", e.summary())
        ok &= bool(with_body)

        b.add_cookies([{"name": "wf_probe", "value": "forge", "url": URL}])
        with b.isolated() as v:
            mode = "shared context, cookies cleared" if getattr(v, "_shared_context", False) else "new context"
            leaked = [c for c in v.cookies() if c["name"] == "wf_probe"]
            print(f"isolation: {mode}; forge cookie visible to verifier: {bool(leaked)}")
            ok &= not leaked
            print(v.goto(URL))
            ok &= len(v.net) > 0
    print(f"total: {time.time() - t0:.1f}s  ->  {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
