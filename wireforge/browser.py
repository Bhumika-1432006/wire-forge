"""A browser session that records the site's own XHR/fetch traffic.

Uses Anakin's Browser API (Playwright over CDP) when ANAKIN_API_KEY is set,
otherwise a local headless Chromium, so development works without a key.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from . import config

BODY_LIMIT = 200_000  # stored in full; network_detail pages through it, so large JSON stays parseable
SHOW_LIMIT = 6000  # characters shown per network_detail call
MAX_ENTRIES = 400
# Map tiles, images and fonts arrive as fetch/xhr on some sites and bury the data calls.
BINARY_TYPES = ("image/", "font/", "video/", "audio/", "protobuf", "octet-stream", "application/pdf")
NOISE_HOSTS = (
    "google-analytics", "googletagmanager", "doubleclick", "facebook", "hotjar",
    "clarity.ms", "segment", "sentry", "newrelic", "nr-data", "adservice", "criteo",
    "bing.com", "tiktok", "snapchat", "mixpanel", "amplitude", "branch.io", "moengage",
    "pinterest", "firebase", "shopifysvc", "monorail", "razorpay", "clevertap", "webengage",
)

SNAPSHOT_JS = r"""
() => {
  const sel = 'a[href], button, input, select, textarea, [role=button], [role=link], [role=tab], [role=option], [onclick]';
  const out = [];
  let n = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    if (r.width === 0 || r.height === 0 || style.visibility === 'hidden' || style.display === 'none') continue;
    const ref = 'e' + (n++);
    el.setAttribute('data-wf-ref', ref);
    const label = (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder')
                   || el.getAttribute('title') || el.getAttribute('name') || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    const tag = el.tagName.toLowerCase();
    const type = el.getAttribute('type') ? `[${el.getAttribute('type')}]` : '';
    const href = tag === 'a' ? ` -> ${el.getAttribute('href').slice(0, 100)}` : '';
    out.push(`${ref} ${tag}${type} "${label}"${href}`);
    if (out.length >= 250) break;
  }
  return out.join('\n');
}
"""

EMBEDDED_JSON_JS = r"""
() => {
  const out = [];
  for (const s of document.querySelectorAll('script[type="application/json"], script[type="application/ld+json"], script#__NEXT_DATA__')) {
    out.push({id: s.id || null, type: s.type, size: s.textContent.length, head: s.textContent.slice(0, 1500)});
  }
  return out.slice(0, 20);
}
"""


@dataclass
class NetEntry:
    idx: int
    method: str
    url: str
    status: int
    resource_type: str
    content_type: str
    request_headers: dict
    post_data: str | None
    body: str | None
    t: float = field(default_factory=time.time)

    def is_graphql(self) -> str:
        post = self.post_data or ""
        if "persistedQuery" in post or "persistedQuery" in self.url:
            return "graphql-persisted"
        if "graphql" in self.url.lower() or post.lstrip().startswith(('{"query"', '[{"query"', '{"operationName"')):
            return "graphql"
        return ""

    def summary(self) -> str:
        size = len(self.body) if self.body else 0
        post = f" body={len(self.post_data)}B" if self.post_data else ""
        tag = f" <{self.is_graphql()}>" if self.is_graphql() else ""
        return f"#{self.idx} {self.method} {self.status} {self.url[:160]} [{self.content_type[:30]}] resp={size}B{post}{tag}"


class BrowserSession:
    def __init__(self, headless: bool = True, parent: "BrowserSession | None" = None):
        self.headless = headless
        self.parent = parent
        self.pw: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.net: list[NetEntry] = []
        self._inflight = 0
        self.backend = "anakin" if config.ANAKIN_API_KEY else "local-chromium"

    def isolated(self) -> "BrowserSession":
        """A second session on the same browser with its own context: no shared cookies or storage."""
        return BrowserSession(self.headless, parent=self)

    # ---------------------------------------------------------------- lifecycle
    def __enter__(self) -> "BrowserSession":
        if self.parent:
            self.browser = self.parent.browser
            assert self.browser and self.parent.context
            self.context = self.browser.new_context(
                user_agent=self.parent.page.evaluate("navigator.userAgent") if self.parent.page else None,
                viewport={"width": 1366, "height": 900},
            )
            self.page = self.context.new_page()
            self._attach(self.page)
            return self
        self.pw = sync_playwright().start()
        if config.ANAKIN_API_KEY:
            self.browser = self.pw.chromium.connect_over_cdp(
                config.ANAKIN_CDP_URL, headers={"X-API-Key": config.ANAKIN_API_KEY}
            )
            self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        else:
            self.browser = self.pw.chromium.launch(headless=self.headless)
            self.context = self.browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1366, "height": 900},
                locale="en-IN",
            )
            self.page = self.context.new_page()
        self._attach(self.page)
        return self

    def __exit__(self, *exc) -> None:
        if self.parent:
            if self.context:
                self.context.close()
            return
        try:
            if self.browser:
                self.browser.close()
        finally:
            if self.pw:
                self.pw.stop()

    # ---------------------------------------------------------------- capture
    def _attach(self, page: Page) -> None:
        page.on("request", self._on_request)
        page.on("requestfinished", self._on_request_done)
        page.on("requestfailed", self._on_request_done)
        page.on("response", self._on_response)

    @staticmethod
    def _tracked(req) -> bool:
        return req.resource_type in ("xhr", "fetch", "document") and not any(
            n in urlparse(req.url).netloc for n in NOISE_HOSTS)

    def _on_request(self, req) -> None:
        if self._tracked(req):
            self._inflight += 1

    def _on_request_done(self, req) -> None:
        if self._tracked(req):
            self._inflight = max(0, self._inflight - 1)

    def _on_response(self, resp) -> None:
        req = resp.request
        if req.resource_type not in ("xhr", "fetch", "document"):
            return
        host = urlparse(req.url).netloc
        if any(n in host for n in NOISE_HOSTS):
            return
        ctype = resp.headers.get("content-type", "")
        if any(b in ctype for b in BINARY_TYPES):
            return
        body = None
        if req.resource_type != "document" and any(k in ctype for k in ("json", "text", "javascript", "xml", "graphql")):
            try:
                body = resp.text()[:BODY_LIMIT]
            except Exception:
                body = None
        headers = {k: v for k, v in req.headers.items() if not k.startswith(":") and k.lower() != "cookie"}
        entry = NetEntry(
            idx=len(self.net), method=req.method, url=req.url, status=resp.status,
            resource_type=req.resource_type, content_type=ctype, request_headers=headers,
            post_data=(req.post_data or None) and req.post_data[:BODY_LIMIT], body=body,
        )
        if len(self.net) < MAX_ENTRIES:
            self.net.append(entry)

    # ---------------------------------------------------------------- tools
    def goto(self, url: str) -> str:
        assert self.page
        self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        self._settle()
        return f"Loaded {self.page.url} — title: {self.page.title()!r}. {len(self.net)} requests captured so far."

    def _settle(self, quiet_ms: int = 700, max_ms: int = 10000) -> None:
        """Wait until no request has been in flight for quiet_ms.

        wait_for_load_state("networkidle") only tracks the initial load, so it returns at once
        after a click and misses the very fetch the click triggered.
        """
        assert self.page
        waited, quiet = 0, 0
        self.page.wait_for_timeout(150)  # let the click's handlers start their requests
        while waited < max_ms and quiet < quiet_ms:
            self.page.wait_for_timeout(100)
            waited += 100
            quiet = quiet + 100 if self._inflight <= 0 else 0

    def snapshot(self) -> str:
        assert self.page
        items = self.page.evaluate(SNAPSHOT_JS)
        return f"URL: {self.page.url}\nTitle: {self.page.title()}\nInteractive elements:\n{items}"

    def page_text(self, max_chars: int = 6000) -> str:
        assert self.page
        text = self.page.evaluate("() => document.body ? document.body.innerText : ''")
        return text[:max_chars]

    def click(self, ref: str) -> str:
        assert self.page
        before = len(self.net)
        self.page.locator(f'[data-wf-ref="{ref}"]').first.click(timeout=10000)
        self._settle()
        return f"Clicked {ref}. Now at {self.page.url}. New requests: {len(self.net) - before} (see network_log since={before})."

    def fill(self, ref: str, text: str, press_enter: bool = False) -> str:
        assert self.page
        before = len(self.net)
        loc = self.page.locator(f'[data-wf-ref="{ref}"]').first
        loc.fill(text, timeout=10000)
        if press_enter:
            loc.press("Enter")
        self._settle()
        return f"Filled {ref}. New requests: {len(self.net) - before} (see network_log since={before})."

    def select(self, ref: str, value: str) -> str:
        assert self.page
        before = len(self.net)
        self.page.locator(f'[data-wf-ref="{ref}"]').first.select_option(value, timeout=10000)
        self._settle()
        return f"Selected {value!r} in {ref}. New requests: {len(self.net) - before}."

    def network_log(self, since: int = 0, contains: str = "", only_json: bool = False) -> str:
        rows = [
            e.summary() for e in self.net[since:]
            if (contains.lower() in e.url.lower() or (e.post_data and contains.lower() in e.post_data.lower()))
            and (not only_json or "json" in e.content_type)
        ]
        return "\n".join(rows[-120:]) or "(no matching requests)"

    def network_detail(self, idx: int, offset: int = 0) -> str:
        """Full request, and the response body from `offset`, SHOW_LIMIT characters at a time."""
        e = self.net[idx]
        body = e.body or ""
        part = body[offset:offset + SHOW_LIMIT]
        more = len(body) - offset - len(part)
        return json.dumps({
            "method": e.method, "url": e.url, "status": e.status, "content_type": e.content_type,
            "kind": e.is_graphql() or None, "request_headers": e.request_headers,
            "post_data": (e.post_data or "")[:SHOW_LIMIT] or None,
            "response_length": len(body), "response_offset": offset, "response_body": part,
            "more": f"{more} more characters: call again with offset={offset + len(part)}" if more > 0 else None,
        }, indent=1)

    def embedded_json(self) -> str:
        assert self.page
        return json.dumps(self.page.evaluate(EMBEDDED_JSON_JS), indent=1)[:8000]

    def cookies(self) -> list[dict]:
        assert self.context
        return self.context.cookies()

    def add_cookies(self, cookies: list[dict]) -> None:
        assert self.context
        self.context.add_cookies(cookies)

    def screenshot(self, path: str) -> str:
        assert self.page
        self.page.screenshot(path=path, full_page=False)
        return path
