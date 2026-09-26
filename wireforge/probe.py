"""Direct HTTP calls the agent uses to test endpoint hypotheses outside the browser."""

from __future__ import annotations

import json
from urllib.parse import urlparse

import httpx

from . import config

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def blocked(url: str) -> str | None:
    path = urlparse(url).path.lower()
    for word in config.BLOCKED_PATH_WORDS:
        if word in path:
            return f"Refused: '{word}' endpoints are out of scope. Wire Forge never pays or places orders."
    return None


def http_request(
    method: str,
    url: str,
    headers: dict | None = None,
    body: str | None = None,
    browser_cookies: list[dict] | None = None,
) -> str:
    if reason := blocked(url):
        return reason
    jar = httpx.Cookies()
    for c in browser_cookies or []:
        jar.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
    h = {"user-agent": UA, "accept": "application/json, text/plain, */*"}
    h.update(headers or {})
    try:
        with httpx.Client(follow_redirects=True, timeout=30, cookies=jar) as client:
            r = client.request(method.upper(), url, headers=h, content=body.encode() if body else None)
    except httpx.HTTPError as exc:
        return f"HTTP error: {exc!r}"
    text = r.text
    try:
        text = json.dumps(r.json(), indent=1)
    except ValueError:
        pass
    return f"status={r.status_code} content-type={r.headers.get('content-type', '')} final_url={r.url}\n{text[:7000]}"
