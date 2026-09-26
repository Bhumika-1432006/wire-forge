"""Browser and HTTP tools shared by the forge and verifier agents."""

from __future__ import annotations

from .agent import Tool
from .browser import BrowserSession
from .probe import http_request


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


S = {"type": "string"}
I = {"type": "integer"}
B = {"type": "boolean"}


def browser_tools(b: BrowserSession) -> list[Tool]:
    return [
        Tool("goto", "Open a URL in the real browser. All XHR/fetch traffic is recorded.",
             _obj({"url": S}, ["url"]), lambda url: b.goto(url)),
        Tool("snapshot", "List visible interactive elements with refs (e0, e1, ...) for click/fill/select.",
             _obj({}, []), lambda: b.snapshot()),
        Tool("page_text", "Visible text of the current page, i.e. what a human sees.",
             _obj({"max_chars": I}, []), lambda max_chars=6000: b.page_text(max_chars)),
        Tool("click", "Click an element by ref from the latest snapshot.",
             _obj({"ref": S}, ["ref"]), lambda ref: b.click(ref)),
        Tool("fill", "Type into an input by ref; optionally press Enter.",
             _obj({"ref": S, "text": S, "press_enter": B}, ["ref", "text"]),
             lambda ref, text, press_enter=False: b.fill(ref, text, press_enter)),
        Tool("select", "Choose an option in a <select> by ref.",
             _obj({"ref": S, "value": S}, ["ref", "value"]), lambda ref, value: b.select(ref, value)),
        Tool("network_log", "One-line summaries of captured requests. Filter by index, URL/body substring, or JSON only.",
             _obj({"since": I, "contains": S, "only_json": B}, []),
             lambda since=0, contains="", only_json=False: b.network_log(since, contains, only_json)),
        Tool("network_detail", "Full request (method, url, headers, post body) and response body for one captured request.",
             _obj({"idx": I}, ["idx"]), lambda idx: b.network_detail(idx)),
        Tool("embedded_json", "JSON the page ships inline (__NEXT_DATA__, ld+json, application/json scripts).",
             _obj({}, []), lambda: b.embedded_json()),
        Tool("http_request",
             "Send an HTTP request directly (not through the page) to test an endpoint hypothesis. "
             "Set use_browser_cookies to reuse the browser session. Checkout/payment paths are refused.",
             _obj({"method": S, "url": S, "headers": {"type": "object"}, "body": S, "use_browser_cookies": B},
                  ["method", "url"]),
             lambda method, url, headers=None, body=None, use_browser_cookies=False: http_request(
                 method, url, headers, body, b.cookies() if use_browser_cookies else None)),
    ]
