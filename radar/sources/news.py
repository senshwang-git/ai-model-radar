from __future__ import annotations

import re

from ..feeds import parse
from ..http import fetch
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


def collect(cfg: dict) -> list[Item]:
    limit = int(cfg.get("per_feed_limit", 30))
    items: list[Item] = []
    for feed in cfg.get("feeds", []):
        name, url = feed["name"], feed["url"]
        try:
            entries = parse(fetch(url, headers={
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"}))
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
