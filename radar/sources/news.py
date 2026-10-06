from __future__ import annotations

import re

import xml.etree.ElementTree as ET

from ..feeds import Entry, parse
from ..http import BROWSER_USER_AGENT, fetch_response
from ..models import Item, to_date


def _matches(text: str, keywords: list[str]) -> bool:
    """Case-insensitive match where each keyword must start a word, so that
    "GPT" does not match "ChatGPT" and "모델" does not match "수치모델"."""
    return any(re.search(r"(?<![\w])" + re.escape(k), text, re.IGNORECASE)
               for k in keywords)


def is_relevant(title: str, summary: str, cfg: dict) -> bool:
    text = f"{title} {summary}"
    return _matches(text, cfg.get("release_keywords", [])) and \
        _matches(text, cfg.get("model_keywords", []))


FEED_ACCEPT = "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8"


def _describe(body: bytes, headers: dict) -> str:
    """Short non-content diagnostic of a response that failed to parse."""
    return (f"content-type={headers.get('content-type', '?')!r}, "
            f"content-encoding={headers.get('content-encoding', '-')!r}, "
            f"len={len(body)}, head={body[:48]!r}")


def fetch_feed(urls: list[str]) -> list[Entry]:
    """Fetch and parse a feed, trying each URL with our agent, then a browser
    agent. Raises with diagnostics of every attempt if all fail."""
    attempts = []
    for url in urls:
        for ua in (None, BROWSER_USER_AGENT):
            headers = {"Accept": FEED_ACCEPT}
            if ua:
                headers["User-Agent"] = ua
            try:
                body, resp_headers = fetch_response(url, headers=headers)
            except Exception as e:
                attempts.append(f"{url} [{'browser' if ua else 'bot'} UA]: {e}")
                continue
            try:
                return parse(body)
            except ET.ParseError as e:
                attempts.append(f"{url} [{'browser' if ua else 'bot'} UA]: {e}; "
                                f"{_describe(body, resp_headers)}")
    raise RuntimeError(" | ".join(attempts))


def collect(cfg: dict) -> list[Item]:
    limit = int(cfg.get("per_feed_limit", 30))
    items: list[Item] = []
    for feed in cfg.get("feeds", []):
        name = feed["name"]
        urls = [feed["url"]] + list(feed.get("fallback_urls", []))
        try:
            entries = fetch_feed(urls)
        except Exception as e:
            print(f"[news] {name}: error {e}")
            continue
        for e in entries[:limit]:
            if not e.id or not e.title:
                continue
            if feed.get("filter", True) and not is_relevant(e.title, e.summary, cfg):
                continue
            items.append(Item(source="news", key=e.id, title=e.title, url=e.link,
                              group=name, detail=e.summary[:160],
                              published=to_date(e.published)))
    return items
